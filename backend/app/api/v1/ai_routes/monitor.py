"""
PMI中国AI项目管理社区 - AI监控仪表盘路由（只读）

提供 LLM 调用统计和 Agent 运行监控指标。
数据来源：AgentSession 表（记录所有 Agent 执行日志）+ LLMCallLog 表（真实 LLM 调用度量）。

容错设计：若表尚未创建或查询异常，返回空默认值而非 502 崩溃。

[PMBOK KA: 跨领域 | PG: 监控 (Monitoring & Controlling) — AI监控仪表盘]
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc, Integer, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError, OperationalError

from app.db.session import get_db
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 空默认返回值 ──────────────────────────────────────────────

_EMPTY_STATS = {
    "total_calls": 0, "total_tokens": 0, "avg_latency_ms": 0,
    "success_rate": 0, "calls_by_provider": {}, "calls_by_agent": {},
    "recent_errors": [], "recent_calls_7d": 0,
    "real_total_calls": 0, "real_total_tokens": 0,
    "real_total_cost_usd": 0, "real_avg_latency_ms": 0, "real_success_rate": 0,
}

_EMPTY_CALLS = {"items": [], "total": 0, "page": 1, "page_size": 20, "total_pages": 0}

_EMPTY_USAGE = {"items": [], "summary": {"total_calls": 0, "total_tokens": 0, "total_cost_usd": 0}}

_EMPTY_TREND = lambda days: {"days": days, "trend": []}


_EMPTY_REALTIME = {
    "today": {"calls": 0, "tokens": 0, "cost_usd": 0, "errors": 0, "error_rate": 0, "avg_latency_ms": 0, "calls_by_provider": {}, "calls_by_task": {}},
    "yesterday": {"calls": 0, "tokens": 0, "cost_usd": 0, "errors": 0, "error_rate": 0, "avg_latency_ms": 0},
    "last_hour": {"calls": 0, "tokens": 0, "cost_usd": 0, "errors": 0},
    "current_hour": {"calls": 0, "tokens": 0, "cost_usd": 0, "errors": 0},
    "this_week": {"calls": 0, "tokens": 0, "cost_usd": 0, "errors": 0},
    "this_month": {"calls": 0, "tokens": 0, "cost_usd": 0, "errors": 0},
    "hourly_today": [],          # 24 项 [{hour, calls, tokens, cost_usd, errors}]
    "cost_by_provider_today": [],  # [{provider, model, calls, tokens, cost_usd}]
    "cost_by_task_today": [],      # [{task_name, calls, tokens, cost_usd, error_rate}]
    "cost_by_project_today": [],   # [{project_id, project_name, calls, tokens, cost_usd}]
    "last_call_at": None,
    "last_call_provider": None,
    "last_call_model": None,
    "comparison": {
        "calls_delta_pct": 0, "cost_delta_pct": 0,
        "tokens_delta_pct": 0, "errors_delta_pct": 0,
    },
    "window_start": None,
    "window_end": None,
}


def _parse_agent_type(title: str) -> str:
    """从 AgentSession.title 中解析 agent_type，如 '[evm] xxx' -> 'evm'"""
    if title and title.startswith("["):
        end = title.find("]")
        if end > 0:
            return title[1:end]
    return "unknown"


# ── 辅助：安全检查表是否存在 ───────────────────────────────────

async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    """检查表是否存在于数据库中"""
    try:
        result = await db.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :name)"),
            {"name": table_name},
        )
        return bool(result.scalar())
    except Exception:
        return False


# ── /ai/monitor/stats ───────────────────────────────────────────

@router.get("/ai/monitor/stats")
async def get_ai_monitor_stats(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """返回 AI / LLM 调用聚合统计（容错：表不存在时返回全零）"""
    # 检查 AgentSession 表
    try:
        has_sessions = await _table_exists(db, "agent_sessions")
    except Exception:
        has_sessions = False

    total_calls = 0
    calls_by_agent: Dict[str, int] = {}
    calls_by_provider: Dict[str, int] = {}
    total_tokens_est = 0
    success_count = 0
    error_count = 0
    recent_errors: List[Dict[str, Any]] = []
    recent_calls = 0

    if has_sessions:
        try:
            from app.models import AgentSession, SystemLLMConfig

            total_calls_result = await db.execute(select(func.count(AgentSession.id)))
            total_calls = total_calls_result.scalar() or 0

            # 分页加载避免 OOM（最多取最近 1000 条用于统计）
            all_sessions = (await db.execute(
                select(AgentSession).order_by(desc(AgentSession.created_at)).limit(1000)
            )).scalars().all()

            for s in all_sessions:
                agent_type = _parse_agent_type(s.title)
                calls_by_agent[agent_type] = calls_by_agent.get(agent_type, 0) + 1

                msgs = s.messages or []
                has_error = False
                for msg in msgs:
                    if isinstance(msg, dict):
                        content = str(msg.get("content", ""))
                        if any(kw in content.lower() for kw in ("error", "exception", "失败")):
                            has_error = True
                        result_summary = str(msg.get("result_summary", ""))
                        if any(kw in result_summary.lower() for kw in ("error", "exception")):
                            has_error = True

                if has_error:
                    error_count += 1
                    if len(recent_errors) < 20:
                        recent_errors.append({
                            "agent_type": agent_type,
                            "title": s.title,
                            "time": s.created_at.isoformat() if s.created_at else None,
                            "session_id": s.id,
                        })
                else:
                    success_count += 1

                for msg in msgs:
                    if isinstance(msg, dict):
                        content_len = len(str(msg.get("content", "")))
                        total_tokens_est += content_len // 2

            # Provider 配置
            try:
                provider_configs = (await db.execute(select(SystemLLMConfig))).scalars().all()
                for cfg in provider_configs:
                    pn = cfg.provider_name or "unknown"
                    if pn not in calls_by_provider:
                        calls_by_provider[pn] = 0
                if calls_by_provider and not any(v > 0 for v in calls_by_provider.values()):
                    for k in calls_by_provider:
                        calls_by_provider[k] = total_calls // max(len(calls_by_provider), 1)
                elif not calls_by_provider:
                    calls_by_provider["minimax"] = total_calls
                    calls_by_provider["openai"] = 0
            except Exception:
                calls_by_provider["minimax"] = total_calls
                calls_by_provider["openai"] = 0

            # 最近7天
            seven_days_ago = datetime.now() - timedelta(days=7)
            recent_count_result = await db.execute(
                select(func.count(AgentSession.id)).where(
                    AgentSession.created_at >= seven_days_ago
                )
            )
            recent_calls = recent_count_result.scalar() or 0

        except (ProgrammingError, OperationalError) as e:
            logger.warning("AgentSession query failed (table may not exist): %s", e)
        except Exception as e:
            logger.error("Unexpected error in /ai/monitor/stats: %s", e)

    avg_latency_ms = 0
    success_rate = round(success_count / max(total_calls, 1), 4) if total_calls else 0

    # 真实 LLM 度量（来自 llm_call_logs）
    real_total_calls = 0
    real_total_tokens = 0
    real_total_cost = 0.0
    real_avg_latency = 0.0
    real_success_rate = 0.0
    try:
        from app.models import LLMCallLog
        agg = (await db.execute(
            select(
                func.count(LLMCallLog.id),
                func.coalesce(func.sum(LLMCallLog.total_tokens), 0),
                func.coalesce(func.sum(LLMCallLog.cost_usd), 0),
                func.coalesce(func.avg(LLMCallLog.latency_ms), 0),
                func.coalesce(
                    func.sum(func.cast(LLMCallLog.status == "success", Integer)) * 1.0
                    / func.nullif(func.count(LLMCallLog.id), 0), 0
                ),
            )
        )).first()
        if agg:
            real_total_calls = agg[0] or 0
            real_total_tokens = int(agg[1] or 0)
            real_total_cost = float(agg[2] or 0)
            real_avg_latency = round(float(agg[3] or 0), 1)
            real_success_rate = round(float(agg[4] or 0), 4)
    except (ProgrammingError, OperationalError) as e:
        logger.warning("LLMCallLog query failed (table may not exist): %s", e)
    except Exception as e:
        logger.error("Unexpected error querying LLMCallLog: %s", e)

    return {
        **_EMPTY_STATS,
        "total_calls": total_calls,
        "total_tokens": total_tokens_est,
        "avg_latency_ms": avg_latency_ms,
        "success_rate": success_rate,
        "calls_by_provider": calls_by_provider,
        "calls_by_agent": calls_by_agent,
        "recent_errors": recent_errors,
        "recent_calls_7d": recent_calls,
        "real_total_calls": real_total_calls,
        "real_total_tokens": real_total_tokens,
        "real_total_cost_usd": round(real_total_cost, 4),
        "real_avg_latency_ms": real_avg_latency,
        "real_success_rate": real_success_rate,
    }


# ── /ai/monitor/calls ───────────────────────────────────────────

@router.get("/ai/monitor/calls")
async def get_ai_monitor_calls(
    provider: Optional[str] = Query(None),
    agent_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """分页返回详细 AI 调用记录（容错）"""
    try:
        has_sessions = await _table_exists(db, "agent_sessions")
    except Exception:
        has_sessions = False

    if not has_sessions:
        return {**_EMPTY_CALLS, "page": page, "page_size": page_size}

    try:
        from app.models import AgentSession

        query = select(AgentSession)
        if agent_type:
            query = query.where(AgentSession.title.like(f"[{agent_type}]%"))

        count_query = select(func.count(AgentSession.id))
        if agent_type:
            count_query = count_query.where(AgentSession.title.like(f"[{agent_type}]%"))
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(desc(AgentSession.created_at))
        query = query.offset((page - 1) * page_size).limit(page_size)
        rows = (await db.execute(query)).scalars().all()

        items = []
        for s in rows:
            atype = _parse_agent_type(s.title or "")
            msgs = s.messages or []

            has_err = False
            result_summary = ""
            for msg in msgs:
                if isinstance(msg, dict):
                    content = str(msg.get("content", ""))
                    if any(kw in content.lower() for kw in ("error", "exception", "失败")):
                        has_err = True
                    summary = msg.get("result_summary", "")
                    if summary:
                        result_summary = summary

            call_status = "error" if has_err else "success"
            if status and call_status != status:
                continue

            items.append({
                "id": s.id,
                "agent_type": atype,
                "title": s.title,
                "summary": result_summary,
                "status": call_status,
                "project_id": s.project_id,
                "user_id": s.user_id,
                "message_count": len(msgs),
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            })

        return {
            "items": items, "total": total, "page": page,
            "page_size": page_size, "total_pages": (total + page_size - 1) // page_size,
        }
    except (ProgrammingError, OperationalError) as e:
        logger.warning("AgentSession calls query failed: %s", e)
        return {**_EMPTY_CALLS, "page": page, "page_size": page_size}
    except Exception as e:
        logger.error("Unexpected error in /ai/monitor/calls: %s", e)
        return {**_EMPTY_CALLS, "page": page, "page_size": page_size}


# ── /ai/monitor/usage ───────────────────────────────────────────

@router.get("/ai/monitor/usage")
async def get_llm_usage(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """按模型聚合 LLM 真实用量（容错）"""
    try:
        has_table = await _table_exists(db, "llm_call_logs")
    except Exception:
        has_table = False

    if not has_table:
        return _EMPTY_USAGE

    try:
        from app.models import LLMCallLog

        rows = (await db.execute(
            select(
                LLMCallLog.provider, LLMCallLog.model,
                func.count(LLMCallLog.id),
                func.coalesce(func.sum(LLMCallLog.total_tokens), 0),
                func.coalesce(func.sum(LLMCallLog.prompt_tokens), 0),
                func.coalesce(func.sum(LLMCallLog.completion_tokens), 0),
                func.coalesce(func.avg(LLMCallLog.latency_ms), 0),
                func.coalesce(func.sum(LLMCallLog.cost_usd), 0),
                func.coalesce(
                    func.sum(func.cast(LLMCallLog.status == "success", Integer)) * 1.0
                    / func.nullif(func.count(LLMCallLog.id), 0), 0
                ),
            ).group_by(LLMCallLog.provider, LLMCallLog.model)
             .order_by(func.sum(LLMCallLog.cost_usd).desc())
        )).all()

        items = []
        for r in rows:
            provider, model, cnt, total_tok, ptok, ctok, avg_lat, cost, sr = r
            items.append({
                "provider": provider, "model": model, "calls": cnt,
                "total_tokens": int(total_tok or 0), "prompt_tokens": int(ptok or 0),
                "completion_tokens": int(ctok or 0), "avg_latency_ms": round(float(avg_lat or 0), 1),
                "total_cost_usd": round(float(cost or 0), 4), "success_rate": round(float(sr or 0), 4),
            })

        grand = (await db.execute(
            select(func.count(LLMCallLog.id),
                  func.coalesce(func.sum(LLMCallLog.total_tokens), 0),
                  func.coalesce(func.sum(LLMCallLog.cost_usd), 0))
        )).first()
        summary = {
            "total_calls": grand[0] or 0,
            "total_tokens": int(grand[1] or 0),
            "total_cost_usd": round(float(grand[2] or 0), 4),
        }
        return {"items": items, "summary": summary}

    except (ProgrammingError, OperationalError) as e:
        logger.warning("LLMCallLog usage query failed: %s", e)
        return _EMPTY_USAGE
    except Exception as e:
        logger.error("Unexpected error in /ai/monitor/usage: %s", e)
        return _EMPTY_USAGE


# ── /ai/monitor/usage/trend ─────────────────────────────────────

@router.get("/ai/monitor/usage/trend")
async def get_llm_usage_trend(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """按天返回 LLM 调用趋势（容错）"""
    try:
        has_table = await _table_exists(db, "llm_call_logs")
    except Exception:
        has_table = False

    if not has_table:
        return _EMPTY_TREND(days)

    try:
        from app.models import LLMCallLog

        start_date = datetime.now() - timedelta(days=days)
        rows = (await db.execute(
            select(
                func.date(LLMCallLog.created_at),
                func.count(LLMCallLog.id),
                func.coalesce(func.sum(LLMCallLog.total_tokens), 0),
                func.coalesce(func.sum(LLMCallLog.cost_usd), 0),
            ).where(LLMCallLog.created_at >= start_date)
             .group_by(func.date(LLMCallLog.created_at))
             .order_by(func.date(LLMCallLog.created_at))
        )).all()

        trend = []
        for r in rows:
            day, cnt, tok, cost = r
            trend.append({
                "date": str(day), "calls": cnt,
                "tokens": int(tok or 0), "cost_usd": round(float(cost or 0), 4),
            })
        return {"days": days, "trend": trend}

    except (ProgrammingError, OperationalError) as e:
        logger.warning("LLMCallLog trend query failed: %s", e)
        return _EMPTY_TREND(days)
    except Exception as e:
        logger.error("Unexpected error in /ai/monitor/usage/trend: %s", e)
        return _EMPTY_TREND(days)


# ── /ai/monitor/ab-test ────────────────────────────────────────

@router.get("/ai/monitor/ab-test")
async def get_llm_ab_test(
    model_a: str = Query(..., description="模型A，格式 provider/model"),
    model_b: str = Query(..., description="模型B，格式 provider/model"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """模型 A/B 对比（容错）"""
    def _parse(m: str):
        if "/" in m:
            p, mo = m.split("/", 1)
            return p, mo
        return m, "%"

    async def _stat(p, mo):
        try:
            from app.models import LLMCallLog
            cond = (LLMCallLog.provider == p)
            if mo != "%":
                cond = cond & (LLMCallLog.model == mo)
            row = (await db.execute(
                select(
                    func.count(LLMCallLog.id),
                    func.coalesce(func.avg(LLMCallLog.latency_ms), 0),
                    func.coalesce(func.sum(LLMCallLog.cost_usd), 0),
                    func.coalesce(func.avg(LLMCallLog.completion_tokens), 0),
                    func.coalesce(
                        func.sum(func.cast(LLMCallLog.status == "success", Integer)) * 1.0
                        / func.nullif(func.count(LLMCallLog.id), 0), 0
                    ),
                ).where(cond)
            )).first()
            if not row or not row[0]:
                return None
            return {
                "calls": row[0], "avg_latency_ms": round(float(row[1] or 0), 1),
                "total_cost_usd": round(float(row[2] or 0), 4),
                "avg_completion_tokens": round(float(row[3] or 0), 1),
                "success_rate": round(float(row[4] or 0), 4),
            }
        except (ProgrammingError, OperationalError):
            return None
        except Exception as e:
            logger.error("AB test stat error for %s/%s: %s", p, mo, e)
            return None

    pa, ma = _parse(model_a)
    pb, mb = _parse(model_b)
    a = await _stat(pa, ma)
    b = await _stat(pb, mb)
    return {"model_a": model_a, "model_b": model_b, "a": a, "b": b}


# ── /ai/monitor/realtime ──────────────────────────────────────

async def _agg_window(db: AsyncSession, start_dt, end_dt):
    """聚合单一时间窗口的 calls/tokens/cost/errors/avg_latency；容错返回全零"""
    try:
        from app.models import LLMCallLog
        row = (await db.execute(
            select(
                func.count(LLMCallLog.id),
                func.coalesce(func.sum(LLMCallLog.total_tokens), 0),
                func.coalesce(func.sum(LLMCallLog.cost_usd), 0),
                func.coalesce(
                    func.sum(func.cast(LLMCallLog.status == "error", Integer)), 0
                ),
                func.coalesce(func.avg(LLMCallLog.latency_ms), 0),
            ).where(LLMCallLog.created_at >= start_dt,
                    LLMCallLog.created_at < end_dt)
        )).first()
        if not row:
            return {"calls": 0, "tokens": 0, "cost_usd": 0, "errors": 0,
                    "error_rate": 0, "avg_latency_ms": 0}
        calls, tokens, cost, errs, avg_lat = row
        calls = int(calls or 0)
        errs = int(errs or 0)
        return {
            "calls": calls,
            "tokens": int(tokens or 0),
            "cost_usd": round(float(cost or 0), 4),
            "errors": errs,
            "error_rate": round(errs / calls, 4) if calls > 0 else 0,
            "avg_latency_ms": round(float(avg_lat or 0), 1),
        }
    except Exception:
        return {"calls": 0, "tokens": 0, "cost_usd": 0, "errors": 0,
                "error_rate": 0, "avg_latency_ms": 0}


@router.get("/ai/monitor/realtime")
async def get_ai_monitor_realtime(
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """实时 + 每日 AI 成本消耗面板

    返回 6 个时间窗（今日/昨日/最近一小时/当前小时/本周/本月）的
    真实 LLM 调用统计，外加 24 小时逐小时明细、按 provider/task/project
    的当日成本切片、最后调用元信息、与昨日环比。

    容错：llm_call_logs 不存在或查询失败时返回 _EMPTY_REALTIME 全零，
    不抛 5xx。
    """
    result = {**_EMPTY_REALTIME}

    try:
        has_table = await _table_exists(db, "llm_call_logs")
    except Exception:
        has_table = False
    if not has_table:
        return result

    try:
        from app.models import LLMCallLog
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        last_hour_start = now - timedelta(hours=1)
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        # 周一为一周起点（ISO 周）
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = today_start.replace(day=1)

        # 6 个时间窗聚合
        today = await _agg_window(db, today_start, now)
        yesterday = await _agg_window(db, yesterday_start, today_start)
        last_hour = await _agg_window(db, last_hour_start, now)
        current_hour = await _agg_window(db, current_hour_start, now)
        this_week = await _agg_window(db, week_start, now)
        this_month = await _agg_window(db, month_start, now)

        # 今日 by_provider / by_task 分布（在 today 节点下作为子字段）
        try:
            by_prov_task = (await db.execute(
                select(
                    LLMCallLog.provider,
                    func.coalesce(func.sum(LLMCallLog.total_tokens), 0),
                ).where(LLMCallLog.created_at >= today_start)
                 .group_by(LLMCallLog.provider)
            )).all()
            today["calls_by_provider"] = {r[0]: int(r[1] or 0) for r in by_prov_task}
        except Exception:
            pass
        try:
            by_task = (await db.execute(
                select(
                    LLMCallLog.task_name,
                    func.count(LLMCallLog.id),
                ).where(LLMCallLog.created_at >= today_start)
                 .group_by(LLMCallLog.task_name)
            )).all()
            today["calls_by_task"] = {(r[0] or "unknown"): int(r[1] or 0) for r in by_task}
        except Exception:
            pass

        # 24 小时逐小时（SQLite: strftime；PostgreSQL: extract）
        # 使用兼容 SQL：func.cast(... as Integer) — SQLite 也支持。
        hourly = []
        try:
            # SQLite 用 strftime('%H', created_at)；这里 try/except 兼容 PG
            hour_expr = func.cast(func.strftime("%H", LLMCallLog.created_at), Integer)
            rows = (await db.execute(
                select(
                    hour_expr.label("hr"),
                    func.count(LLMCallLog.id),
                    func.coalesce(func.sum(LLMCallLog.total_tokens), 0),
                    func.coalesce(func.sum(LLMCallLog.cost_usd), 0),
                    func.coalesce(
                        func.sum(func.cast(LLMCallLog.status == "error", Integer)), 0
                    ),
                ).where(LLMCallLog.created_at >= today_start)
                 .group_by("hr").order_by("hr")
            )).all()
            bucket = {int(r[0]): {
                "hour": int(r[0]),
                "calls": int(r[1] or 0),
                "tokens": int(r[2] or 0),
                "cost_usd": round(float(r[3] or 0), 4),
                "errors": int(r[4] or 0),
            } for r in rows if r[0] is not None}
            # 填满 0-23 缺位（让 24 根柱图永远画完整）
            hourly = [bucket.get(h, {"hour": h, "calls": 0, "tokens": 0, "cost_usd": 0, "errors": 0})
                      for h in range(24)]
        except Exception as e:
            logger.warning("hourly bucket query failed: %s", e)
            hourly = [{"hour": h, "calls": 0, "tokens": 0, "cost_usd": 0, "errors": 0} for h in range(24)]

        # 当日按 provider×model 成本 TOP
        cost_by_provider_today = []
        try:
            rows = (await db.execute(
                select(
                    LLMCallLog.provider, LLMCallLog.model,
                    func.count(LLMCallLog.id),
                    func.coalesce(func.sum(LLMCallLog.total_tokens), 0),
                    func.coalesce(func.sum(LLMCallLog.cost_usd), 0),
                ).where(LLMCallLog.created_at >= today_start)
                 .group_by(LLMCallLog.provider, LLMCallLog.model)
                 .order_by(func.sum(LLMCallLog.cost_usd).desc())
                 .limit(20)
            )).all()
            cost_by_provider_today = [
                {"provider": r[0], "model": r[1], "calls": int(r[2] or 0),
                 "tokens": int(r[3] or 0), "cost_usd": round(float(r[4] or 0), 4)}
                for r in rows
            ]
        except Exception as e:
            logger.warning("cost_by_provider_today query failed: %s", e)

        # 当日按 task_name 成本（task_name 即 agent 类型字段）
        cost_by_task_today = []
        try:
            rows = (await db.execute(
                select(
                    LLMCallLog.task_name,
                    func.count(LLMCallLog.id),
                    func.coalesce(func.sum(LLMCallLog.total_tokens), 0),
                    func.coalesce(func.sum(LLMCallLog.cost_usd), 0),
                    func.coalesce(
                        func.sum(func.cast(LLMCallLog.status == "error", Integer)), 0
                    ),
                ).where(LLMCallLog.created_at >= today_start)
                 .group_by(LLMCallLog.task_name)
                 .order_by(func.sum(LLMCallLog.cost_usd).desc())
                 .limit(20)
            )).all()
            cost_by_task_today = [
                {"task_name": r[0] or "unknown", "calls": int(r[1] or 0),
                 "tokens": int(r[2] or 0), "cost_usd": round(float(r[3] or 0), 4),
                 "error_rate": round((int(r[4] or 0) / int(r[1] or 1)), 4) if int(r[1] or 0) > 0 else 0}
                for r in rows
            ]
        except Exception as e:
            logger.warning("cost_by_task_today query failed: %s", e)

        # 当日按 project_id 成本
        cost_by_project_today = []
        try:
            from app.models import Project
            rows = (await db.execute(
                select(
                    LLMCallLog.project_id,
                    Project.name,
                    func.count(LLMCallLog.id),
                    func.coalesce(func.sum(LLMCallLog.total_tokens), 0),
                    func.coalesce(func.sum(LLMCallLog.cost_usd), 0),
                ).outerjoin(Project, Project.id == LLMCallLog.project_id)
                 .where(LLMCallLog.created_at >= today_start)
                 .group_by(LLMCallLog.project_id, Project.name)
                 .order_by(func.sum(LLMCallLog.cost_usd).desc())
                 .limit(20)
            )).all()
            cost_by_project_today = [
                {"project_id": r[0], "project_name": r[1] or "(无项目)",
                 "calls": int(r[2] or 0), "tokens": int(r[3] or 0),
                 "cost_usd": round(float(r[4] or 0), 4)}
                for r in rows
            ]
        except Exception as e:
            logger.warning("cost_by_project_today query failed: %s", e)

        # 最后一次调用
        last_call_at = None
        last_call_provider = None
        last_call_model = None
        try:
            row = (await db.execute(
                select(LLMCallLog.created_at, LLMCallLog.provider, LLMCallLog.model)
                .order_by(desc(LLMCallLog.created_at)).limit(1)
            )).first()
            if row:
                last_call_at = row[0].isoformat() if row[0] else None
                last_call_provider = row[1]
                last_call_model = row[2]
        except Exception:
            pass

        # 环比：今日 vs 昨日（百分比，昨日为 0 时返回 None/0）
        def _pct(today_v, yesterday_v):
            if yesterday_v == 0:
                return 0 if today_v == 0 else 100  # 昨日为0、今日>0 → 标 100%
            return round(((today_v - yesterday_v) / yesterday_v) * 100, 2)

        comparison = {
            "calls_delta_pct": _pct(today["calls"], yesterday["calls"]),
            "cost_delta_pct": _pct(today["cost_usd"], yesterday["cost_usd"]),
            "tokens_delta_pct": _pct(today["tokens"], yesterday["tokens"]),
            "errors_delta_pct": _pct(today["errors"], yesterday["errors"]),
        }

        result.update({
            "today": today,
            "yesterday": yesterday,
            "last_hour": last_hour,
            "current_hour": current_hour,
            "this_week": this_week,
            "this_month": this_month,
            "hourly_today": hourly,
            "cost_by_provider_today": cost_by_provider_today,
            "cost_by_task_today": cost_by_task_today,
            "cost_by_project_today": cost_by_project_today,
            "last_call_at": last_call_at,
            "last_call_provider": last_call_provider,
            "last_call_model": last_call_model,
            "comparison": comparison,
            "window_start": today_start.isoformat(),
            "window_end": now.isoformat(),
        })
        return result

    except (ProgrammingError, OperationalError) as e:
        logger.warning("/ai/monitor/realtime query failed: %s", e)
        return result
    except Exception as e:
        logger.error("Unexpected error in /ai/monitor/realtime: %s", e)
        return result

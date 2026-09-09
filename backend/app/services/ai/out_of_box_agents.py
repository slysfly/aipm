"""
PMI中国AI项目管理社区 - 开箱即用的领域 Agent 实现

将上一轮规划的差异化能力落地为真实可调用的 Agent：
- weekly_report      自动周报（基于真实任务/风险/复盘数据统计 + LLM 润色）
- risk               风险识别（扫描逾期/低进度/临近截止任务，LLM 生成风险清单并可选落库）
- meeting_minutes    会议纪要转任务（解析纪要中的行动项，自动建任务）
- wbs                WBS 生成（LLM 生成多级分解并落库根任务）
- evm                EVM 挣值分析（真实 PV/EV/AC/CPI/SPI）
- resource           资源优化（负载热力 + 调配建议）
- compliance        合规审计（流程合规检查）
- quality            质量检查（测试/缺陷趋势）

所有 Agent 调用都会把执行记录写入 AgentSession（title 以 [agent_type] 前缀），
供 AgentPanel 真实遥测使用。

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: AI Management — 预制AI Agent]"""
from __future__ import annotations
from sqlalchemy import text

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, Integer, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_engine import ai_engine
from app.models import (
    Task, Project, User, Risk, AgentSession,
    TaskStatus, TaskPriority,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def _safe_json(text: str) -> Any:
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    m = re.search(r"[\[{].*[\]}]", t, re.DOTALL)
    if m:
        t = m.group(0)
    try:
        return json.loads(t)
    except Exception:
        return None


async def _llm(prompt: str, temperature: float = 0.3, max_tokens: int = 1600, timeout: int = 60, retries: int = 2) -> Optional[str]:
    """调用系统默认大模型；无配置/失败返回 None，由调用方降级处理。

    增加 asyncio.wait_for 超时保护，避免 LLM 调用卡死整个 Agent 流程。
    显式指定 provider='minimax'，因为默认 provider('openai') 在服务器上未配置有效密钥。
    增加重试（retries）以应对 provider 瞬时网络/限流错误，提升稳定性。
    """
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return await asyncio.wait_for(
                ai_engine.generate(prompt, provider="minimax", temperature=temperature, max_tokens=max_tokens),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            last_err = f"timeout({timeout}s)"
            logger.warning("LLM 调用超时 (attempt=%d/%d, timeout=%ss)", attempt, retries, timeout)
        except Exception as e:  # noqa: BLE001
            last_err = repr(e)
            logger.warning("LLM 调用异常 (attempt=%d/%d): %s", attempt, retries, e)
        if attempt < retries:
            await asyncio.sleep(min(1.5 * attempt, 4))
    logger.error("LLM 调用最终失败: %s (prompt_len=%d)", last_err, len(prompt))
    return None


async def _log_agent_run(
    db: AsyncSession, user_id: str, project_id: Optional[str],
    agent_type: str, summary: str, result: Dict[str, Any],
) -> None:
    """把一次 Agent 执行写入 AgentSession，供前端真实遥测。"""
    try:
        session = AgentSession(
            user_id=user_id,
            project_id=project_id,
            title=f"[{agent_type}] {summary}",
            messages=[{
                "role": "system",
                "content": f"agent_run:{agent_type}",
                "timestamp": datetime.now().isoformat(),
                "result_summary": summary,
            }],
        )
        db.add(session)
        await db.commit()
    except Exception:
        await db.rollback()


async def _resolve_user(db: AsyncSession, name: str) -> Optional[str]:
    if not name:
        return None
    res = await db.execute(
        select(User).where((User.username == name) | (User.full_name == name) | (User.email == name))
    )
    u = res.scalar_one_or_none()
    return u.id if u else None


async def _wbs_seq(db: AsyncSession, project_id: str) -> int:
    cnt = (await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id, Task.parent_task_id.is_(None), Task.is_deleted.is_(False)
        )
    )).scalar() or 0
    return cnt + 1


async def _create_task(
    db: AsyncSession, project_id: str, name: str,
    assignee_id: Optional[str] = None, planned_end: Optional[datetime] = None,
    priority: int = TaskPriority.MEDIUM.value, description: str = "",
    category: Optional[str] = None, labels: Optional[list] = None,
) -> Task:
    seq = await _wbs_seq(db, project_id)
    task = Task(
        project_id=project_id,
        wbs_code=str(seq),
        name=name[:255],
        status=TaskStatus.TODO.value,
        priority=priority,
        assignee_id=assignee_id,
        planned_end=planned_end,
        description=description,
        category=category,
        labels=labels or [],
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


def _parse_due(text: str) -> Optional[datetime]:
    if not text:
        return None
    patterns = (
        (r"(\d{4}-\d{2}-\d{2})", "date"),
        (r"(\d{1,2})月(\d{1,2})[日号]", "md"),
        (r"周([一二三四五六日天])", "week"),
    )
    for pat, kind in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        try:
            if kind == "date":
                return datetime.fromisoformat(m.group(1))
            if kind == "md":
                now = datetime.now()
                return now.replace(month=int(m.group(1)), day=int(m.group(2)))
            wmap = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
            days_ahead = (wmap[m.group(1)] - datetime.now().weekday()) % 7 or 7
            return datetime.now() + timedelta(days=days_ahead)
        except Exception:
            return None
    return None


# --------------------------------------------------------------------------- #
# 统计辅助
# --------------------------------------------------------------------------- #
async def _project_stats(db: AsyncSession, project_id: str) -> Dict[str, Any]:
    rows = (await db.execute(
        select(
            func.count(Task.id),
            func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)),
            func.avg(Task.progress),
        ).where(Task.project_id == project_id, Task.is_deleted.is_(False))
    )).one()
    total, done, avg = rows[0] or 0, rows[1] or 0, rows[2] or 0

    overdue = (await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id, Task.is_deleted.is_(False),
            Task.planned_end < datetime.now(), Task.status != TaskStatus.DONE.value,
        )
    )).scalar() or 0

    risk_cnt = (await db.execute(
        select(func.count(Risk.id)).where(Risk.project_id == project_id)
    )).scalar() or 0

    return {
        "total": int(total), "done": int(done),
        "in_progress": int(total) - int(done),
        "overdue": int(overdue), "avg_progress": round(float(avg or 0), 1),
        "risk_count": int(risk_cnt),
    }


# --------------------------------------------------------------------------- #
# Agent 实现
# --------------------------------------------------------------------------- #
async def run_weekly_report(
    db: AsyncSession, user_id: str, project_id: Optional[str], weeks: int = 1
) -> Dict[str, Any]:
    proj = (await db.get(Project, project_id)) if project_id else None
    scope = "全公司项目" if not project_id else (proj.name if proj else project_id)
    stats: Dict[str, Any] = {"projects": 0}
    if project_id:
        stats = await _project_stats(db, project_id)
        stats["project_name"] = scope
    else:
        projs = (await db.execute(select(Project).where(Project.is_deleted.is_(False)))).scalars().all()
        stats["projects"] = len(projs)
        agg = {"total": 0, "done": 0, "overdue": 0, "risk_count": 0}
        for p in projs:
            s = await _project_stats(db, p.id)
            for k in ("total", "done", "overdue", "risk_count"):
                agg[k] += s[k]
        stats.update(agg)

    llm_text = await _llm(
        f"你是一名资深项目经理。请基于以下真实数据，生成一份专业、简洁的"
        f"{weeks}周项目状态报告（中文，分『整体进展』『风险与问题』『下周计划建议』三段，不超过400字）：\n"
        f"数据：{json.dumps(stats, ensure_ascii=False)}"
    )
    report = llm_text or (
        f"【自动周报】\n整体进展：共 {stats.get('total', stats.get('projects', 0))} 项任务，"
        f"已完成 {stats.get('done', 0)} 项，平均进度 {stats.get('avg_progress', 0)}%。\n"
        f"风险与问题：逾期 {stats.get('overdue', 0)} 项，登记风险 {stats.get('risk_count', 0)} 条。\n"
        f"建议：优先清理逾期任务，召开风险评审会。（未配置大模型，已生成模板化报告）"
    )
    await _log_agent_run(db, user_id, project_id, "report", f"周报::{scope}", {"stats": stats})
    return {"report": report, "stats": stats, "scope": scope}


async def run_risk_identification(
    db: AsyncSession, user_id: str, project_id: Optional[str], create: bool = False
) -> Dict[str, Any]:
    if not project_id:
        return {"error": "风险识别需要指定项目"}
    tasks = (await db.execute(
        select(Task).where(
            Task.project_id == project_id, Task.is_deleted.is_(False),
            Task.status != TaskStatus.DONE.value,
        ).order_by(Task.planned_end.asc()).limit(40)
    )).scalars().all()

    existing = (await db.execute(
        select(Risk).where(Risk.project_id == project_id)
    )).scalars().all()
    existing_names = {r.name for r in existing}

    task_brief = "\n".join(
        f"- {t.name} | 状态:{t.status} | 进度:{float(t.progress or 0)}% | 截止:{t.planned_end.date() if t.planned_end else '未定'}"
        for t in tasks[:25]
    ) or "（无进行中任务）"

    llm = await _llm(
        "你是风险管理专家。基于以下项目任务清单，识别 TOP5 潜在风险，"
        "严格按 JSON 数组返回，每项含：name(风险名)、description(说明)、"
        "probability(0-1)、impact(0-1)、recommendation(应对策略)。不要解释。\n"
        f"任务清单：\n{task_brief}"
    )
    risks = _safe_json(llm) if llm else None
    if not isinstance(risks, list):
        # 降级：基于逾期/低进度规则生成风险
        risks = []
        for t in tasks:
            if t.planned_end and t.planned_end < datetime.now():
                risks.append({
                    "name": f"任务「{t.name}」逾期", "description": "已超过计划截止日期仍未完成",
                    "probability": 0.8, "impact": 0.6,
                    "recommendation": "立即重新排期并升级处理",
                })
            elif float(t.progress or 0) < 30:
                risks.append({
                    "name": f"任务「{t.name}」进度滞后", "description": "进度低于30%且未完工",
                    "probability": 0.6, "impact": 0.5,
                    "recommendation": "增加资源或调整范围",
                })
        risks = risks[:5]

    created = []
    for r in risks:
        name = str(r.get("name", "")).strip()
        if not name or name in existing_names:
            continue
        try:
            prob = max(0.0, min(1.0, float(r.get("probability", 0.5))))
            imp = max(0.0, min(1.0, float(r.get("impact", 0.5))))
        except Exception:
            prob, imp = 0.5, 0.5
        if create:
            risk = Risk(
                project_id=project_id, name=name[:255],
                description=r.get("description", ""),
                probability=prob, impact=imp, risk_score=round(prob * imp, 4),
                category="technical", status="identified",
            )
            db.add(risk)
            await db.flush()
            created.append(risk.id)
        else:
            created.append(None)

    await _log_agent_run(db, user_id, project_id, "risk", f"识别风险::{len(risks)}条", {"count": len(risks)})
    await db.commit()
    return {"risks": risks, "created_count": sum(1 for c in created if c), "created_ids": [c for c in created if c]}


async def run_meeting_minutes_to_tasks(
    db: AsyncSession, user_id: str, project_id: Optional[str], minutes: str, create: bool = True
) -> Dict[str, Any]:
    if not project_id:
        return {"error": "会议纪要转任务需要指定项目"}
    llm = await _llm(
        "你是会议纪要做任务助手。从纪要中提取所有行动项，严格按 JSON 数组返回，"
        "每项含：name(任务名)、assignee(负责人姓名,可为空)、due(截止日描述,如'周五'/'2026-08-01',可为空)、"
        "priority(1-5,默认3)、description(说明)。不要解释。\n纪要：\n" + minutes
    )
    items = _safe_json(llm) if llm else None
    if not isinstance(items, list):
        # 降级：按行解析「负责人/截止」模式
        items = []
        for line in minutes.splitlines():
            line = line.strip().lstrip("-•*0123456789.、").strip()
            if len(line) < 4:
                continue
            items.append({"name": line, "assignee": "", "due": "", "priority": 3, "description": line})

    created = []
    for it in items[:30]:
        name = str(it.get("name", "")).strip()
        if not name:
            continue
        assignee_id = await _resolve_user(db, it.get("assignee", ""))
        due = _parse_due(str(it.get("due", "")))
        try:
            pri = int(it.get("priority", 3))
            pri = max(1, min(5, pri))
        except Exception:
            pri = 3
        if create:
            t = await _create_task(
                db, project_id, name, assignee_id=assignee_id, planned_end=due,
                priority=pri, description=it.get("description", ""), category="meeting_action",
            )
            created.append({"id": t.id, "name": t.name})
        else:
            created.append({"id": None, "name": name})

    await _log_agent_run(db, user_id, project_id, "wbs", f"纪要转任务::{len(created)}项", {"count": len(created)})
    await db.commit()
    return {"tasks": items, "created": created, "created_count": sum(1 for c in created if c.get("id"))}


async def run_wbs(
    db: AsyncSession, user_id: str, project_id: Optional[str], objective: str
) -> Dict[str, Any]:
    if not project_id:
        return {"error": "WBS 生成需要指定项目"}
    llm = await _llm(
        f"你是 WBS 分解专家（遵循项目管理标准）。针对目标：{objective}\n"
        "生成一级工作分解（最多8项），严格按 JSON 数组返回，每项含 name(工作包名)、"
        "description(说明)、priority(1-5)。不要解释。"
    )
    items = _safe_json(llm) if llm else None
    if not isinstance(items, list):
        items = [{"name": objective, "description": "根工作包", "priority": 3}]
    created = []
    for it in items[:8]:
        name = str(it.get("name", "")).strip()
        if not name:
            continue
        try:
            pri = int(it.get("priority", 3)); pri = max(1, min(5, pri))
        except Exception:
            pri = 3
        t = await _create_task(
            db, project_id, name, priority=pri,
            description=it.get("description", ""), category="wbs",
        )
        created.append({"id": t.id, "name": t.name})
    await _log_agent_run(db, user_id, project_id, "wbs", f"WBS::{len(created)}项", {"count": len(created)})
    await db.commit()
    return {"wbs": items, "created": created, "created_count": len(created)}


async def run_evm(db: AsyncSession, user_id: str, project_id: Optional[str]) -> Dict[str, Any]:
    if not project_id:
        return {"error": "EVM 分析需要指定项目"}
    rows = (await db.execute(
        select(
            func.coalesce(func.sum(Task.planned_value), 0),
            func.coalesce(func.sum(Task.earned_value), 0),
            func.coalesce(func.sum(Task.actual_cost), 0),
            func.count(Task.id),
            func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)),
        ).where(Task.project_id == project_id, Task.is_deleted.is_(False))
    )).one()
    pv, ev, ac, total, done = float(rows[0] or 0), float(rows[1] or 0), float(rows[2] or 0), rows[3] or 0, rows[4] or 0
    cpi = round(ev / ac, 3) if ac else None
    spi = round(ev / pv, 3) if pv else None
    await _log_agent_run(db, user_id, project_id, "evm", "EVM挣值分析", {"cpi": cpi, "spi": spi})
    return {
        "pv": pv, "ev": ev, "ac": ac,
        "cpi": cpi, "spi": spi,
        "total_tasks": int(total), "done_tasks": int(done),
        "health": ("健康" if (cpi and cpi >= 0.95 and spi and spi >= 0.95) else "需关注"),
    }


async def run_resource_optimize(db: AsyncSession, user_id: str, project_id: Optional[str]) -> Dict[str, Any]:
    if not project_id:
        return {"error": "资源优化需要指定项目"}
    tasks = (await db.execute(
        select(Task).where(
            Task.project_id == project_id, Task.is_deleted.is_(False),
            Task.status != TaskStatus.DONE.value, Task.assignee_id != None
        )
    )).scalars().all()
    load: Dict[str, int] = {}
    for t in tasks:
        load[t.assignee_id] = load.get(t.assignee_id, 0) + 1
    overloaded = sorted(load.items(), key=lambda x: -x[1])[:5]
    names = {u.id: (u.full_name or u.username) for u in (await db.execute(
        select(User).where(User.id.in_(list(load.keys())))
    )).scalars().all()} if load else {}
    suggestions = [
        f"{names.get(uid, uid)} 当前承担 {cnt} 项未完成任务，建议分流"
        for uid, cnt in overloaded if cnt >= 3
    ] or ["当前资源负载均衡，无显著瓶颈"]
    await _log_agent_run(db, user_id, project_id, "resource", "资源优化分析", {"overloaded": len(overloaded)})
    return {"load": {names.get(k, k): v for k, v in load.items()}, "suggestions": suggestions}


async def run_compliance_audit(db: AsyncSession, user_id: str, project_id: Optional[str]) -> Dict[str, Any]:
    if not project_id:
        return {"error": "合规审计需要指定项目"}
    p = await db.get(Project, project_id)
    has_risk = (await db.execute(select(func.count(Risk.id)).where(Risk.project_id == project_id))).scalar() or 0
    try:
        from app.models.pm_extras import Lesson
    except Exception:
        Lesson = None  # 模块缺失时不影响合规审计主流程
    has_lesson = 0
    if Lesson is not None:
        has_lesson = (await db.execute(
            select(func.count(case((True, 1), else_=0))).select_from(Lesson)
            .where(Lesson.project_name == (p.name if p else ""))
        )).scalar() or 0
    findings = []
    if p and not p.start_date:
        findings.append("项目缺少明确的启动日期（启动过程组不完整）")
    if has_risk == 0:
        findings.append("未登记任何风险（风险管理过程缺失）")
    if has_lesson == 0:
        findings.append("暂无经验教训沉淀（收尾过程组待加强）")
    findings.append("✅ 任务闭环与权限模型已就绪") if not findings else None
    findings = [f for f in findings if f]
    score = max(0, 100 - len(findings) * 15)
    await _log_agent_run(db, user_id, project_id, "compliance", f"合规审计::{score}分", {"score": score})
    return {"score": score, "findings": findings, "areas": ["启动", "规划", "执行", "监控", "收尾"]}


async def run_quality_check(db: AsyncSession, user_id: str, project_id: Optional[str]) -> Dict[str, Any]:
    if not project_id:
        return {"error": "质量检查需要指定项目"}
    testing = (await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id, Task.is_deleted.is_(False),
            Task.status == TaskStatus.TESTING.value,
        )
    )).scalar() or 0
    total = (await db.execute(
        select(func.count(Task.id)).where(Task.project_id == project_id, Task.is_deleted.is_(False))
    )).scalar() or 0
    await _log_agent_run(db, user_id, project_id, "quality", "质量检查", {"testing": testing})
    return {"testing_tasks": int(testing), "total_tasks": int(total),
            "advice": "测试任务占比偏低，建议加强质量门禁" if testing / max(total, 1) < 0.15 else "测试覆盖良好"}


# --------------------------------------------------------------------------- #
# 新增 Agent: 项目健康检查 (Agent 9)
# --------------------------------------------------------------------------- #
async def run_health_check(db: AsyncSession, user_id: str, project_id: Optional[str]) -> Dict[str, Any]:
    """综合检查项目的进度/成本/风险/质量状态，输出健康评分（0-100）"""
    if not project_id:
        return {"error": "健康检查需要指定项目"}

    p = await db.get(Project, project_id)
    if not p:
        return {"error": "项目不存在"}

    # 任务统计
    task_rows = (await db.execute(
        select(
            func.count(Task.id),
            func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)),
            func.sum(case((Task.status == TaskStatus.IN_PROGRESS.value, 1), else_=0)),
            func.sum(case((Task.status == TaskStatus.TODO.value, 1), else_=0)),
            func.sum(case((Task.planned_end < text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), 1), else_=0)),
            func.avg(Task.progress),
        ).where(Task.project_id == project_id, Task.is_deleted.is_(False))
    )).one()
    total, done, in_progress, todo, overdue, avg_progress = (
        task_rows[0] or 0, task_rows[1] or 0, task_rows[2] or 0,
        task_rows[3] or 0, task_rows[4] or 0, float(task_rows[5] or 0),
    )

    # 风险统计
    risk_rows = (await db.execute(
        select(
            func.count(Risk.id),
            func.sum(case((Risk.status != "closed", 1), else_=0)),
            func.avg(Risk.risk_score),
        ).where(Risk.project_id == project_id)
    )).one()
    risk_total, risk_active, avg_risk_score = (
        risk_rows[0] or 0, risk_rows[1] or 0, float(risk_rows[2] or 0),
    )

    # EVM 数据
    evm_rows = (await db.execute(
        select(
            func.coalesce(func.sum(Task.planned_value), 0),
            func.coalesce(func.sum(Task.earned_value), 0),
            func.coalesce(func.sum(Task.actual_cost), 0),
        ).where(Task.project_id == project_id, Task.is_deleted.is_(False))
    )).one()
    pv, ev, ac = float(evm_rows[0] or 0), float(evm_rows[1] or 0), float(evm_rows[2] or 0)
    cpi = round(ev / ac, 3) if ac else 1.0
    spi = round(ev / pv, 3) if pv else 1.0

    # 进度维得分 (0-25)
    progress_pct = done / max(total, 1) * 100
    schedule_score = min(25, (progress_pct / 100) * 15 + (spi if spi else 1) * 10)
    if overdue > 0:
        schedule_score = max(0, schedule_score - overdue * 3)

    # 成本维得分 (0-25)
    if cpi and cpi >= 1.0:
        cost_score = 25
    elif cpi and cpi >= 0.9:
        cost_score = 20
    elif cpi and cpi >= 0.8:
        cost_score = 15
    elif cpi and cpi >= 0.7:
        cost_score = 10
    else:
        cost_score = 5

    # 风险维得分 (0-25)
    if risk_total == 0:
        risk_score_dim = 15  # 没有登记风险反而是隐患
    else:
        risk_score_dim = max(0, 25 - risk_active * 3 - int(avg_risk_score * 20))
    risk_score_dim = max(0, min(25, risk_score_dim))

    # 质量维得分 (0-25)
    testing_tasks = (await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id, Task.is_deleted.is_(False),
            Task.status == TaskStatus.TESTING.value,
        )
    )).scalar() or 0
    quality_ratio = testing_tasks / max(total, 1)
    quality_score = min(25, quality_ratio * 50 + (1 - (overdue / max(total, 1))) * 15)
    quality_score = max(0, min(25, quality_score))

    total_score = round(schedule_score + cost_score + risk_score_dim + quality_score, 1)
    total_score = max(0, min(100, total_score))

    # 生成健康等级
    if total_score >= 80:
        level = "健康"
    elif total_score >= 60:
        level = "需关注"
    elif total_score >= 40:
        level = "亚健康"
    else:
        level = "危险"

    # 用 LLM 生成更丰富的分析
    health_data = {
        "score": total_score, "level": level,
        "dimensions": {
            "schedule": {"score": round(schedule_score, 1), "max": 25,
                         "total_tasks": int(total), "done": int(done),
                         "overdue": int(overdue), "spi": spi},
            "cost": {"score": round(cost_score, 1), "max": 25,
                     "cpi": cpi, "pv": pv, "ev": ev, "ac": ac},
            "risk": {"score": round(risk_score_dim, 1), "max": 25,
                     "total": int(risk_total), "active": int(risk_active),
                     "avg_score": avg_risk_score},
            "quality": {"score": round(quality_score, 1), "max": 25,
                        "testing_tasks": int(testing_tasks), "total_tasks": int(total)},
        },
    }

    llm_text = await _llm(
        f"你是一名资深项目健康评估专家。基于以下项目健康检查数据，生成一段简洁的专业评估意见（中文，100字以内），"
        f"指出主要问题和改进方向：\n{json.dumps(health_data, ensure_ascii=False)}"
    )
    assessment = llm_text or (
        f"项目整体{level}（评分{total_score}分）。"
        f"进度维度：完成{progress_pct:.0f}%，{overdue}项逾期；"
        f"成本维度：CPI={cpi}；"
        f"风险维度：{risk_active}个活跃风险；"
        f"建议：优先清理逾期任务，加强风险跟踪。"
    )

    await _log_agent_run(db, user_id, project_id, "health_check",
                         f"健康检查::{level}({total_score}分)", {"score": total_score, "level": level})

    return {
        "health_data": health_data,
        "assessment": assessment,
        "score": total_score,
        "level": level,
    }


# --------------------------------------------------------------------------- #
# 新增 Agent: 智能决策建议 (Agent 10)
# --------------------------------------------------------------------------- #
async def run_decision_advice(db: AsyncSession, user_id: str, project_id: Optional[str]) -> Dict[str, Any]:
    """基于项目当前状态，给出3-5条可执行的决策建议"""
    if not project_id:
        return {"error": "决策建议需要指定项目"}

    p = await db.get(Project, project_id)
    if not p:
        return {"error": "项目不存在"}

    # 收集项目数据
    task_rows = (await db.execute(
        select(
            func.count(Task.id),
            func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)),
            func.sum(case((Task.status == TaskStatus.IN_PROGRESS.value, 1), else_=0)),
            func.sum(case((Task.status == TaskStatus.TODO.value, 1), else_=0)),
            func.avg(Task.progress),
        ).where(Task.project_id == project_id, Task.is_deleted.is_(False))
    )).one()
    total, done, in_progress, todo, avg_progress = (
        task_rows[0] or 0, task_rows[1] or 0, task_rows[2] or 0,
        task_rows[3] or 0, float(task_rows[4] or 0),
    )

    overdue = (await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id, Task.is_deleted.is_(False),
            Task.planned_end < text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), Task.status != TaskStatus.DONE.value,
        )
    )).scalar() or 0

    # EVM
    evm_rows = (await db.execute(
        select(
            func.coalesce(func.sum(Task.planned_value), 0),
            func.coalesce(func.sum(Task.earned_value), 0),
            func.coalesce(func.sum(Task.actual_cost), 0),
        ).where(Task.project_id == project_id, Task.is_deleted.is_(False))
    )).one()
    pv, ev, ac = float(evm_rows[0] or 0), float(evm_rows[1] or 0), float(evm_rows[2] or 0)
    cpi = round(ev / ac, 3) if ac else None
    spi = round(ev / pv, 3) if pv else None

    # 风险
    risk_active = (await db.execute(
        select(func.count(Risk.id)).where(
            Risk.project_id == project_id, Risk.status != "closed"
        )
    )).scalar() or 0

    # 资源负载
    tasks_in_work = (await db.execute(
        select(Task).where(
            Task.project_id == project_id, Task.is_deleted.is_(False),
            Task.status.in_([TaskStatus.IN_PROGRESS.value, TaskStatus.IN_REVIEW.value]),
            Task.assignee_id != None,
        )
    )).scalars().all()
    load: Dict[str, int] = {}
    for t in tasks_in_work:
        load[t.assignee_id] = load.get(t.assignee_id, 0) + 1
    overloaded = sum(1 for cnt in load.values() if cnt >= 3)

    # 构建项目快照
    snapshot = {
        "project_name": p.name,
        "project_status": p.status,
        "tasks": {"total": int(total), "done": int(done), "in_progress": int(in_progress),
                   "todo": int(todo), "overdue": int(overdue), "avg_progress": round(avg_progress, 1)},
        "evm": {"cpi": cpi, "spi": spi, "pv": pv, "ev": ev, "ac": ac},
        "risks": {"active": int(risk_active)},
        "resources": {"overloaded_members": overloaded},
        "budget": {"budget": float(p.budget or 0), "actual_cost": float(p.actual_cost or 0)},
    }

    # LLM 生成决策建议
    llm_text = await _llm(
        "你是一名资深项目管理顾问。基于以下项目快照数据，给出3-5条可执行的决策建议。"
        "按 JSON 数组返回，每项含：title(决策标题), priority(高/中/低), "
        "description(具体建议,50-100字), expected_impact(预期效果)。"
        "不要解释，只返回 JSON。\n项目数据：\n" + json.dumps(snapshot, ensure_ascii=False),
        temperature=0.4, max_tokens=2000
    )

    suggestions = _safe_json(llm_text) if llm_text else None
    if not isinstance(suggestions, list) or len(suggestions) == 0:
        # 降级：基于规则生成3条建议
        suggestions = []
        if overdue > 0:
            suggestions.append({
                "title": "清理逾期任务",
                "priority": "高",
                "description": f"当前有 {overdue} 项任务已逾期，建议立即召开进度会议，逐项评估并重新排期，必要时申请资源支持。",
                "expected_impact": "消除进度滞后，恢复项目节奏",
            })
        if cpi is not None and cpi < 0.9:
            suggestions.append({
                "title": "成本管控预警",
                "priority": "高",
                "description": f"成本绩效指数 CPI={cpi}，低于警戒线 0.9。建议审查超支工作包，控制变更请求，优化资源利用率。",
                "expected_impact": "遏制成本恶化趋势",
            })
        if risk_active > 3:
            suggestions.append({
                "title": "强化风险管理",
                "priority": "中",
                "description": f"当前有 {risk_active} 个活跃风险，建议召开风险评审会，为高概率/高影响风险制定应对预案。",
                "expected_impact": "降低风险发生概率和影响",
            })
        if overloaded > 0:
            suggestions.append({
                "title": "资源负载均衡",
                "priority": "中",
                "description": f"有 {overloaded} 名成员承担过多任务（≥3项），建议识别瓶颈资源，调配或引入外部支援。",
                "expected_impact": "提升团队效率，防止过劳",
            })
        if not suggestions:
            suggestions.append({
                "title": "保持当前策略",
                "priority": "低",
                "description": "项目各项指标正常，建议持续监控关键绩效指标，定期复盘总结经验教训。",
                "expected_impact": "维持项目健康运行",
            })

    await _log_agent_run(db, user_id, project_id, "decision",
                         f"决策建议::{len(suggestions)}条", {"count": len(suggestions)})

    return {
        "suggestions": suggestions,
        "snapshot": snapshot,
        "suggestion_count": len(suggestions),
    }


# --------------------------------------------------------------------------- #
# 统一调度
# --------------------------------------------------------------------------- #
DISPATCH = {
    "weekly_report": run_weekly_report,
    "report": run_weekly_report,
    "risk": run_risk_identification,
    "meeting_minutes": run_meeting_minutes_to_tasks,
    "wbs": run_wbs,
    "evm": run_evm,
    "resource": run_resource_optimize,
    "compliance": run_compliance_audit,
    "quality": run_quality_check,
    "health_check": run_health_check,
    "decision": run_decision_advice,
}

AGENT_INPUT_HINT = {
    "weekly_report": "可选 project_id / weeks",
    "risk": "project_id 必填，create=true 可落库",
    "meeting_minutes": "project_id + input(纪要文本)，create=true 建任务",
    "wbs": "project_id + input(目标)",
    "evm": "project_id",
    "resource": "project_id",
    "compliance": "project_id",
    "quality": "project_id",
    "health_check": "project_id 必填，综合健康检查输出评分",
    "decision": "project_id 必填，生成智能决策建议",
}


async def run_agent(
    agent_type: str, db: AsyncSession, user_id: str,
    project_id: Optional[str], input_text: str = "", options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # PMBOK 过程 Agent：pmbok:<过程id>（如 pmbok:4.1）
    if agent_type.startswith("pmbok:"):
        from app.services.ai.pmbok_agents import run_pmbok_process
        pid = agent_type.split(":", 1)[1]
        return await run_pmbok_process(
            pid, db, user_id, project_id, input_text=input_text, options=options,
        )

    fn = DISPATCH.get(agent_type)
    if not fn:
        raise ValueError(f"未知 Agent 类型: {agent_type}")
    opts = options or {}
    try:
        if agent_type in ("weekly_report", "report"):
            result = await fn(db, user_id, project_id, weeks=int(opts.get("weeks", 1)))
        elif agent_type == "risk":
            result = await fn(db, user_id, project_id, create=bool(opts.get("create", False)))
        elif agent_type == "meeting_minutes":
            result = await fn(db, user_id, project_id, input_text or "", create=bool(opts.get("create", True)))
        elif agent_type == "wbs":
            result = await fn(db, user_id, project_id, input_text or "")
        else:
            result = await fn(db, user_id, project_id)
    except asyncio.TimeoutError:
        logger.error("Agent 执行超时 (agent_type=%s, project_id=%s)", agent_type, project_id)
        raise RuntimeError(f"Agent [{agent_type}] 执行超时，请稍后重试")
    except (ValueError, RuntimeError):
        raise  # 已知的业务/超时错误，原样上抛
    except Exception as e:
        logger.exception("Agent 执行异常 (agent_type=%s, project_id=%s)", agent_type, project_id)
        raise RuntimeError(f"Agent [{agent_type}] 执行失败：{type(e).__name__} {str(e)[:200]}")
    return result

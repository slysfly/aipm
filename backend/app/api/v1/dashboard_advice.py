"""
仪表盘 · AI 下一步建议（Next-Step Advisor）

[PMI 知识体系]
- PMP  (PMBOK 指南第六版十大知识领域): 范围/进度/成本/质量/资源/沟通/风险/采购/相关方 + 整合
- PMI-ACP (敏捷实践指南): 迭代交付、看板、价值流、团队赋能
- CPMAI (PMI 认证人工智能项目管理): 业务理解→数据治理→模型运营→持续监测的 AI 治理闭环

本端点依据上述框架，结合「当前项目进展」的多维实时数据，预判项目健康度，
并自动生成可执行的下一步建议。无大模型配置时降级为规则引擎（同样覆盖全维度）。
"""

from __future__ import annotations
from sqlalchemy import text

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_active_user, get_current_user
from app.db.session import get_db
from app.models import Project, Risk, Task, TaskStatus, User
from app.models.knowledge_base import KnowledgeBase
from app.services.ai.out_of_box_agents import _llm, _safe_json
from app.services.rag_engine import get_rag_engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 内存缓存：避免每次刷新都调 LLM（3.7G VPS 上 LLM 调用会触发 OOM）
# ---------------------------------------------------------------------------
_NEXT_STEPS_CACHE: Dict[str, Dict[str, Any]] = {}  # key -> {data, ts}
_CACHE_TTL = 900  # 15 分钟缓存（仪表盘不需要实时）


def _cache_key(user_id: str, scope: str, project_id: Optional[str]) -> str:
    return f"{user_id}:{scope}:{project_id or 'all'}"


def _get_cache(key: str) -> Optional[Dict[str, Any]]:
    entry = _NEXT_STEPS_CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    if entry:
        del _NEXT_STEPS_CACHE[key]
    return None


def _set_cache(key: str, data: Dict[str, Any]) -> None:
    _NEXT_STEPS_CACHE[key] = {"data": data, "ts": time.time()}
    # 简单清理：超过 50 条时清掉最旧的
    if len(_NEXT_STEPS_CACHE) > 50:
        oldest = min(_NEXT_STEPS_CACHE, key=lambda k: _NEXT_STEPS_CACHE[k]["ts"])
        del _NEXT_STEPS_CACHE[oldest]
from app.services.kb_access import get_accessible_kb_ids

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/dashboard",
    tags=["仪表盘"],
    dependencies=[Depends(get_current_active_user)],
)


# --------------------------------------------------------------------------- #
# 请求 / 响应模型
# --------------------------------------------------------------------------- #
class NextStepRequest(BaseModel):
    project_id: Optional[str] = None     # 不传 -> 分析全部进行中项目（组合视角）
    kb_scope: str = "mine"               # mine=仅我的知识库 | all=全部可见库（管理员）
    include_kb: bool = False             # 是否结合知识库 RAG（默认关闭：embedding 加载会吃大量内存）
    use_ai: bool = False                 # 是否强制调用大模型（默认关闭，小内存 VPS 上会 OOM）


# --------------------------------------------------------------------------- #
# 维度快照采集
# --------------------------------------------------------------------------- #
def _empty_snapshot() -> Dict[str, Any]:
    return {
        "project_id": "", "project_name": "", "project_type": "", "status": "",
        "has_scope": False, "wbs_depth": 0,
        "task_total": 0, "task_done": 0, "task_in_progress": 0, "task_todo": 0,
        "task_testing": 0, "overdue": 0, "avg_progress": 0.0,
        "ev_pv": 0.0, "ev_ev": 0.0, "ev_ac": 0.0, "cpi": None, "spi": None,
        "risk_total": 0, "risk_active": 0, "avg_risk_score": 0.0,
        "change_total": 0,
        "automation_count": 0, "active_sprints": 0, "integration_count": 0,
        "budget": 0.0, "actual_cost": 0.0,
        "start_date": None, "end_date": None,
    }


async def _collect_snapshots(
    db: AsyncSession, projects: List[Project]
) -> List[Dict[str, Any]]:
    """对一批项目做高效批量聚合，返回每个项目的多维快照。

    可选模型（变更/审批/自动化/迭代/集成）按需惰性导入并容错，缺表不影响主流程。
    """
    # 惰性导入可选模型
    try:
        from app.models.pm_extras import ChangeRequest
    except Exception:
        ChangeRequest = None
    try:
        from app.models.automation import Automation
    except Exception:
        Automation = None
    try:
        from app.models.sprint import Sprint
    except Exception:
        Sprint = None
    try:
        from app.models.integration import Integration
    except Exception:
        Integration = None

    pids = [p.id for p in projects]
    snaps: Dict[str, Dict[str, Any]] = {}
    for p in projects:
        s = _empty_snapshot()
        s["project_id"] = p.id
        s["project_name"] = p.name
        s["project_type"] = getattr(p, "project_type", "") or ""
        s["status"] = getattr(p, "status", "") or ""
        s["has_scope"] = bool(getattr(p, "description", None))
        s["budget"] = float(getattr(p, "budget", 0) or 0)
        s["actual_cost"] = float(getattr(p, "actual_cost", 0) or 0)
        s["start_date"] = p.start_date.isoformat() if getattr(p, "start_date", None) else None
        s["end_date"] = p.end_date.isoformat() if getattr(p, "end_date", None) else None
        snaps[p.id] = s

    if not pids:
        return list(snaps.values())

    # --- 1) 任务状态计数（批量） ---
    try:
        rows = (await db.execute(
            select(Task.project_id, Task.status, func.count(Task.id))
            .where(Task.is_deleted.is_(False), Task.project_id.in_(pids))
            .group_by(Task.project_id, Task.status)
        )).all()
        for pid, status, cnt in rows:
            s = snaps.get(pid)
            if not s:
                continue
            s["task_total"] += cnt
            if status == TaskStatus.DONE.value:
                s["task_done"] += cnt
            elif status == TaskStatus.IN_PROGRESS.value:
                s["task_in_progress"] += cnt
            elif status == TaskStatus.TODO.value:
                s["task_todo"] += cnt
            elif status == TaskStatus.TESTING.value:
                s["task_testing"] += cnt
        # WBS 深度（根任务 vs 子任务）
        depth_rows = (await db.execute(
            select(Task.project_id, func.count(Task.id))
            .where(Task.is_deleted.is_(False), Task.project_id.in_(pids),
                   Task.parent_task_id.is_(None))
            .group_by(Task.project_id)
        )).all()
        for pid, cnt in depth_rows:
            s = snaps.get(pid)
            if s:
                s["wbs_depth"] = cnt
    except Exception as e:
        logger.warning("任务聚合失败: %s", e)

    # --- 2) 逾期任务（批量） ---
    try:
        rows = (await db.execute(
            select(Task.project_id, func.count(Task.id))
            .where(Task.is_deleted.is_(False), Task.project_id.in_(pids),
                   Task.planned_end < func.now(), Task.status != TaskStatus.DONE.value)
            .group_by(Task.project_id)
        )).all()
        for pid, cnt in rows:
            s = snaps.get(pid)
            if s:
                s["overdue"] = cnt
    except Exception as e:
        logger.warning("逾期聚合失败: %s", e)

    # --- 3) EVM 与平均进度（批量） ---
    try:
        rows = (await db.execute(
            select(
                Task.project_id,
                func.coalesce(func.sum(Task.planned_value), 0),
                func.coalesce(func.sum(Task.earned_value), 0),
                func.coalesce(func.sum(Task.actual_cost), 0),
                func.coalesce(func.avg(Task.progress), 0),
            )
            .where(Task.is_deleted.is_(False), Task.project_id.in_(pids))
            .group_by(Task.project_id)
        )).all()
        for pid, pv, ev, ac, avg in rows:
            s = snaps.get(pid)
            if not s:
                continue
            s["ev_pv"] = float(pv or 0)
            s["ev_ev"] = float(ev or 0)
            s["ev_ac"] = float(ac or 0)
            s["avg_progress"] = round(float(avg or 0), 1)
            s["cpi"] = round(ev / ac, 3) if ac else None
            s["spi"] = round(ev / pv, 3) if pv else None
    except Exception as e:
        logger.warning("EVM 聚合失败: %s", e)

    # --- 4) 风险（批量） ---
    try:
        rows = (await db.execute(
            select(Risk.project_id, func.count(Risk.id),
                   func.coalesce(func.avg(Risk.risk_score), 0))
            .where(Risk.project_id.in_(pids))
            .group_by(Risk.project_id)
        )).all()
        for pid, cnt, avg_score in rows:
            s = snaps.get(pid)
            if not s:
                continue
            s["risk_total"] = cnt
            s["avg_risk_score"] = round(float(avg_score or 0), 3)
            s["risk_active"] = cnt  # 简化：未单独维护 closed 状态时以总数计
    except Exception as e:
        logger.warning("风险聚合失败: %s", e)

    # --- 5) 变更：本系统 ChangeRequest 不以 project_id 直接关联，保持 0。
    #        "采购与变更"维度改以 integration_count（外部集成=采购代理）作为信号。

    # --- 7) 自动化规则（批量，容错） ---
    if Automation is not None:
        try:
            rows = (await db.execute(
                select(Automation.project_id, func.count(Automation.id))
                .where(Automation.project_id.in_(pids))
                .group_by(Automation.project_id)
            )).all()
            for pid, cnt in rows:
                s = snaps.get(pid)
                if s:
                    s["automation_count"] = cnt
        except Exception as e:
            logger.warning("自动化聚合失败: %s", e)

    # --- 8) 活跃迭代 / Sprint（批量，容错） ---
    if Sprint is not None:
        try:
            rows = (await db.execute(
                select(Sprint.project_id, func.count(Sprint.id))
                .where(Sprint.project_id.in_(pids), Sprint.status == "active")
                .group_by(Sprint.project_id)
            )).all()
            for pid, cnt in rows:
                s = snaps.get(pid)
                if s:
                    s["active_sprints"] = cnt
        except Exception:
            try:
                rows = (await db.execute(
                    select(Sprint.project_id, func.count(Sprint.id))
                    .where(Sprint.project_id.in_(pids))
                    .group_by(Sprint.project_id)
                )).all()
                for pid, cnt in rows:
                    s = snaps.get(pid)
                    if s:
                        s["active_sprints"] = cnt
            except Exception as e:
                logger.warning("Sprint 聚合失败: %s", e)

    # 组合视角聚合（integration 为全局概念，作为采购/外部协同代理指标）
    if Integration is not None:
        try:
            conn = (await db.execute(
                select(func.count(Integration.id)).where(Integration.status == "connected")
            )).scalar() or 0
            for s in snaps.values():
                s["integration_count"] = int(conn)
        except Exception as e:
            logger.warning("集成聚合失败: %s", e)

    return list(snaps.values())


# --------------------------------------------------------------------------- #
# 组合视角聚合
# --------------------------------------------------------------------------- #
def _aggregate_portfolio(snaps: List[Dict[str, Any]]) -> Dict[str, Any]:
    agg = _empty_snapshot()
    agg["project_name"] = f"组合视角（{len(snaps)} 个项目）"
    for s in snaps:
        agg["task_total"] += s["task_total"]
        agg["task_done"] += s["task_done"]
        agg["task_in_progress"] += s["task_in_progress"]
        agg["task_todo"] += s["task_todo"]
        agg["task_testing"] += s["task_testing"]
        agg["overdue"] += s["overdue"]
        agg["risk_total"] += s["risk_total"]
        agg["risk_active"] += s["risk_active"]
        agg["change_total"] += s["change_total"]
        agg["automation_count"] += s["automation_count"]
        agg["active_sprints"] += s["active_sprints"]
        agg["ev_pv"] += s["ev_pv"]
        agg["ev_ev"] += s["ev_ev"]
        agg["ev_ac"] += s["ev_ac"]
        agg["budget"] += s["budget"]
        agg["actual_cost"] += s["actual_cost"]
        if not s["has_scope"]:
            agg["has_scope"] = False
    # 组合级 CPI/SPI
    agg["cpi"] = round(agg["ev_ev"] / agg["ev_ac"], 3) if agg["ev_ac"] else None
    agg["spi"] = round(agg["ev_ev"] / agg["ev_pv"], 3) if agg["ev_pv"] else None
    agg["avg_progress"] = round(
        (agg["task_done"] / agg["task_total"] * 100) if agg["task_total"] else 0, 1
    )
    agg["avg_risk_score"] = round(
        (sum(s["avg_risk_score"] for s in snaps) / len(snaps)) if snaps else 0, 3
    )
    return agg


# --------------------------------------------------------------------------- #
# 规则降级：覆盖全维度的建议
# --------------------------------------------------------------------------- #
def _rule_recommendations(
    snap: Dict[str, Any], scope: str
) -> List[Dict[str, Any]]:
    """无大模型时，依据硬指标生成覆盖 PMI 全维度的可执行建议。"""
    recs: List[Dict[str, Any]] = []
    name = snap.get("project_name", "项目")

    if snap["overdue"] > 0:
        recs.append({
            "dimension": "进度管理", "framework": "PMP",
            "priority": "高",
            "title": f"清理 {snap['overdue']} 项逾期任务",
            "rationale": f"「{name}」存在 {snap['overdue']} 项已超过计划截止日期的未完成任务，SPI={snap['spi']}，进度已偏离基线。",
            "actions": [
                "逐项目/任务召开进度评审会，识别逾期根因（依赖、资源、范围蔓延）",
                "对关键路径任务重新排期并升级处理，必要时申请资源或缩减范围",
                "在系统中将逾期任务标记为风险并纳入每日站会跟踪",
            ],
            "expected_outcome": "恢复进度节奏，SPI 回升至 0.95 以上。",
        })

    if snap["cpi"] is not None and snap["cpi"] < 0.95:
        recs.append({
            "dimension": "成本管理", "framework": "PMP",
            "priority": "高" if snap["cpi"] < 0.9 else "中",
            "title": "成本绩效预警与纠偏",
            "rationale": f"CPI={snap['cpi']} 低于健康线 0.95，实际成本已超支（预算 {snap['budget']}，实际 {snap['actual_cost']}）。",
            "actions": [
                "审查超支工作包，定位成本偏差最大的任务",
                "收紧变更控制，所有新增范围走正式变更流程",
                "优化资源利用率，减少加班与返工",
            ],
            "expected_outcome": "遏制成本恶化，CPI 回到 1.0 附近。",
        })

    if snap["risk_total"] == 0:
        recs.append({
            "dimension": "风险管理", "framework": "PMP",
            "priority": "中",
            "title": "建立风险登记册",
            "rationale": f"「{name}」尚未登记任何风险，风险管理过程缺失，存在被动救火隐患。",
            "actions": [
                "召开风险识别工作坊，覆盖技术/进度/成本/相关方维度",
                "为每个风险录入概率与影响，计算风险分数并排序",
                "为高分数风险制定应对策略与责任人",
            ],
            "expected_outcome": "形成可跟踪的风险台账，提升项目韧性。",
        })
    elif snap["risk_active"] >= 3:
        recs.append({
            "dimension": "风险管理", "framework": "PMP",
            "priority": "中",
            "title": "强化风险应对与监控",
            "rationale": f"当前有 {snap['risk_active']} 个活跃风险（平均风险分 {snap['avg_risk_score']}），需常态化监控。",
            "actions": [
                "召开风险评审会，复核高概率/高影响风险的应对预案",
                "为 TOP3 风险指定_owner_与触发阈值，进入双周回顾",
                "将已闭环风险及时归档，保持登记册整洁",
            ],
            "expected_outcome": "降低风险发生概率与影响，减少突发问题。",
        })

    if not snap["has_scope"]:
        recs.append({
            "dimension": "范围管理", "framework": "PMP",
            "priority": "中",
            "title": "补齐范围基准与 WBS",
            "rationale": f"「{name}」缺少项目描述/范围说明，范围管理过程不完整，易引发范围蔓延。",
            "actions": [
                "撰写项目章程与范围说明书，明确可交付成果与验收标准",
                "使用 AI 生成 WBS 并拆解到可执行工作包",
                "建立范围变更控制流程",
            ],
            "expected_outcome": "范围清晰、可度量，减少范围蔓延。",
        })

    if snap["task_testing"] / max(snap["task_total"], 1) < 0.15:
        recs.append({
            "dimension": "质量管理", "framework": "PMP",
            "priority": "中",
            "title": "加强质量门禁",
            "rationale": f"测试类任务占比 {round(snap['task_testing']/max(snap['task_total'],1)*100,1)}%，低于 15% 的健康水位。",
            "actions": [
                "在关键里程碑前设置质量门禁（测试用例通过率、缺陷密度）",
                "引入自动化测试与代码评审",
                "建立缺陷趋势看板并定期复盘",
            ],
            "expected_outcome": "缺陷率下降，交付质量稳定。",
        })

    if snap["active_sprints"] > 0 and snap["project_type"] in ("agile", "scrum"):
        recs.append({
            "dimension": "敏捷交付", "framework": "ACP",
            "priority": "中",
            "title": "优化迭代价值流",
            "rationale": f"项目采用敏捷模式，当前有 {snap['active_sprints']} 个活跃迭代。",
            "actions": [
                "每个 Sprint 明确可交付的『已完成的定义(DoD)』",
                "用看板可视化在制品(WIP)，限制在制以缩短交付周期",
                "每个迭代结束做回顾，沉淀改进项并落地",
            ],
            "expected_outcome": "交付节奏稳定，团队_velocity_可预测。",
        })

    if snap["automation_count"] == 0 and snap["integration_count"] == 0:
        recs.append({
            "dimension": "AI 治理与数据资产", "framework": "CPMAI",
            "priority": "低",
            "title": "启动 AI 治理与自动化闭环",
            "rationale": f"「{name}」尚未配置自动化规则或外部集成，AI 与数据资产利用率偏低。",
            "actions": [
                "建立项目知识库并上传历史文档，沉淀组织过程资产",
                "配置自动化规则（如逾期自动提醒、状态流转）",
                "将复盘经验沉淀为知识库，形成 CPMAI 的『模型运营化』闭环",
            ],
            "expected_outcome": "减少重复性人工操作，经验可复用。",
        })

    if snap["change_total"] > 0:
        recs.append({
            "dimension": "采购与变更", "framework": "PMP",
            "priority": "中",
            "title": "规范变更与采购控制",
            "rationale": f"当前有 {snap['change_total']} 个进行中的变更/采购事项，需确保受控。",
            "actions": [
                "所有变更进入变更控制委员会(CCB)评审，记录影响评估",
                "外部采购明确 SOW 与验收节点",
                "定期回顾变更趋势，识别系统性范围问题",
            ],
            "expected_outcome": "变更透明可控，减少范围蔓延与成本溢出。",
        })

    if not recs:
        recs.append({
            "dimension": "整合管理", "framework": "PMP",
            "priority": "低",
            "title": "保持监控与持续改进",
            "rationale": f"「{name}」各项指标处于健康区间（平均进度 {snap['avg_progress']}%）。",
            "actions": [
                "持续监控关键绩效指标(CPI/SPI/风险分)",
                "定期复盘并沉淀经验教训到知识库",
                "保持与相关方的节奏化沟通",
            ],
            "expected_outcome": "维持项目健康运行。",
        })

    # 排序：高 > 中 > 低
    order = {"高": 0, "中": 1, "低": 2}
    recs.sort(key=lambda r: order.get(r["priority"], 1))
    return recs[:8]


# --------------------------------------------------------------------------- #
# 维度健康度评估（规则，用于前端展示）
# --------------------------------------------------------------------------- #
def _dimension_scores(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    dims = []

    # 进度
    prog = snap["avg_progress"]
    sched_score = 10 if snap["overdue"] == 0 else max(2, 10 - snap["overdue"])
    if snap["spi"] and snap["spi"] < 0.9:
        sched_score = min(sched_score, 4)
    dims.append({"name": "进度管理", "framework": "PMP",
                 "status": "健康" if sched_score >= 8 else ("需关注" if sched_score >= 5 else "危险"),
                 "score": sched_score})

    # 成本
    if snap["cpi"] is None:
        cost_score = 7
    elif snap["cpi"] >= 1.0:
        cost_score = 10
    elif snap["cpi"] >= 0.95:
        cost_score = 8
    elif snap["cpi"] >= 0.9:
        cost_score = 6
    else:
        cost_score = 3
    dims.append({"name": "成本管理", "framework": "PMP",
                 "status": "健康" if cost_score >= 8 else ("需关注" if cost_score >= 5 else "危险"),
                 "score": cost_score})

    # 质量
    qr = snap["task_testing"] / max(snap["task_total"], 1)
    q_score = 10 if qr >= 0.2 else (7 if qr >= 0.15 else 4)
    dims.append({"name": "质量管理", "framework": "PMP",
                 "status": "健康" if q_score >= 8 else ("需关注" if q_score >= 5 else "危险"),
                 "score": q_score})

    # 资源（以逾期/在制近似）
    r_score = 8 if snap["overdue"] == 0 else 5
    dims.append({"name": "资源管理", "framework": "PMP",
                 "status": "健康" if r_score >= 8 else "需关注", "score": r_score})

    # 风险
    if snap["risk_total"] == 0:
        risk_score = 5
    else:
        risk_score = max(2, 10 - snap["risk_active"] - int(snap["avg_risk_score"] * 4))
    risk_score = max(0, min(10, risk_score))
    dims.append({"name": "风险管理", "framework": "PMP",
                 "status": "健康" if risk_score >= 8 else ("需关注" if risk_score >= 5 else "危险"),
                 "score": risk_score})

    # 范围
    sc_score = 9 if snap["has_scope"] and snap["wbs_depth"] > 0 else 4
    dims.append({"name": "范围管理", "framework": "PMP",
                 "status": "健康" if sc_score >= 8 else "需关注", "score": sc_score})

    # 沟通（无审批待办指标，按固定健康分）
    comm_score = 8
    dims.append({"name": "沟通管理", "framework": "PMP",
                 "status": "健康", "score": comm_score})

    # 采购/变更
    pc_score = 8 if snap["change_total"] == 0 else 6
    dims.append({"name": "采购与变更", "framework": "PMP",
                 "status": "健康" if pc_score >= 8 else "需关注", "score": pc_score})

    # 相关方
    st_score = 8
    dims.append({"name": "相关方管理", "framework": "PMP",
                 "status": "健康", "score": st_score})

    # 敏捷
    ag_score = 9 if snap["active_sprints"] > 0 else 6
    dims.append({"name": "敏捷交付", "framework": "ACP",
                 "status": "健康" if ag_score >= 8 else "需关注", "score": ag_score})

    # AI 治理
    ai_score = 9 if (snap["automation_count"] > 0 or snap.get("integration_count", 0) > 0) else 5
    dims.append({"name": "AI 治理与数据资产", "framework": "CPMAI",
                 "status": "健康" if ai_score >= 8 else "需关注", "score": ai_score})

    return dims


# --------------------------------------------------------------------------- #
# 端点
# --------------------------------------------------------------------------- #
@router.post("/next-steps")
async def next_steps(
    payload: NextStepRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成仪表盘『下一步建议』：多维快照 + 知识库 RAG + 系统大模型（PMP/ACP/CPMAI 框架）。

    - project_id 为空：组合视角，分析全部进行中项目。
    - 无大模型 / 解析失败：降级为规则引擎，仍覆盖 PMI 全维度。
    """
    # 1) 选取目标项目
    if payload.project_id:
        proj = await db.get(Project, payload.project_id)
        if not proj or getattr(proj, "is_deleted", False):
            raise HTTPException(status_code=404, detail="项目不存在")
        projects = [proj]
        scope = "project"
    else:
        result = await db.execute(
            select(Project).where(
                Project.is_deleted.is_(False), Project.status == "active"
            ).order_by(Project.updated_at.desc()).limit(20)
        )
        projects = list(result.scalars().all())
        scope = "portfolio"
        # 组合视角若无进行中项目，则回退到任意非删除项目
        if not projects:
            result = await db.execute(
                select(Project).where(Project.is_deleted.is_(False)).limit(20)
            )
            projects = list(result.scalars().all())

    if not projects:
        raise HTTPException(status_code=404, detail="暂无可分析的项目，请先创建项目")

    # 2) 采集多维快照
    snaps = await _collect_snapshots(db, projects)
    snap = snaps[0] if scope == "project" else _aggregate_portfolio(snaps)
    snap_for_prompt = snap if scope == "project" else {
        **snap,
        "per_project": [
            {k: v for k, v in s.items() if k in (
                "project_name", "status", "task_total", "task_done", "overdue",
                "avg_progress", "cpi", "spi", "risk_total", "change_total",
            )} for s in snaps
        ],
    }

    # 3) 知识库 RAG 增强（使用可访问的可见知识库集合）
    context = ""
    kb_ids: List[str] = []
    if payload.include_kb:
        try:
            kb_ids = await get_accessible_kb_ids(db, current_user, scope=payload.kb_scope or "mine")
            if kb_ids:
                engine = await get_rag_engine(db)
                topic = snap.get("project_name", "项目管理")
                context = await engine.get_context(topic, kb_ids, top_k=5, max_tokens=2000)
        except Exception as e:
            logger.warning("知识库 RAG 召回失败: %s", e)
            context = ""

    # 4) 维度评分（用于前端展示）
    dimensions = _dimension_scores(snap)
    health_score = sum(d["score"] for d in dimensions)  # 11 维 × 10 = 110 上限

    # 5) 组装大模型提示词
    prompt = f"""你是一名同时持有 PMI-PMP、PMI-ACP 与 CPMAI 认证的首席项目顾问。
请基于下方【项目实时数据】（含组合/单项目多维指标，以及可选的【知识库参考】），
站在 PMBOK 十大知识领域 + 敏捷(ACP) + AI 治理(CPMAI) 的体系视角，预判项目健康度，
并自动生成可执行的下一步建议。

【项目实时数据】
<<<<DATA>>>>
{json.dumps(snap_for_prompt, ensure_ascii=False, default=str)}
<<<<END>>>

【知识库参考内容】（可能为空）
<<<<CONTEXT>>>>
{context or '（无相关知识库内容）'}
<<<<END>>>

要求：
1. overall_assessment：一段中文总体研判（50-100字），点明最紧迫的风险与机会。
2. dimensions：对以下 11 个维度逐一评估，每项给 0-10 分与状态(健康/需关注/危险)：
   范围管理、进度管理、成本管理、质量管理、资源管理、沟通管理、风险管理、采购与变更、相关方管理、敏捷交付(ACP)、AI治理与数据资产(CPMAI)。
3. recommendations：生成 3-5 条下一步执行建议，每条覆盖一个维度，并对标相应框架。
4. frameworks_used：本次实际用到的框架集合（如 ["PMP","ACP","CPMAI"]）。

严格只输出一个 JSON 对象（不要代码围栏、不要额外解释）：
{{
  "overall_assessment": "string",
  "dimensions": [
    {{"name": "维度名", "framework": "PMP/ACP/CPMAI", "status": "健康/需关注/危险", "score": 0-10}}
  ],
  "recommendations": [
    {{
      "dimension": "维度名",
      "framework": "PMP/ACP/CPMAI",
      "priority": "高/中/低",
      "title": "建议标题",
      "rationale": "为什么（结合上方数据）",
      "actions": ["步骤1", "步骤2"],
      "expected_outcome": "预期成效"
    }}
  ],
  "frameworks_used": ["PMP", "ACP", "CPMAI"]
}}"""

    # ---- 缓存检查 ----
    ck = _cache_key(str(current_user.id), scope, payload.project_id)
    cached = _get_cache(ck)
    if cached:
        logger.info("next-steps: 命中缓存 key=%s", ck)
        return cached

    # ---- LLM 调用（默认禁用：3.7G VPS 上 MiniMax 会触发 OOM）----
    # 如需启用，将下面的 False 改为 True，或通过 payload.use_ai=True 触发
    raw = None
    if getattr(payload, 'use_ai', False):
        try:
            raw = await _llm(prompt, temperature=0.3, max_tokens=1024, timeout=25, retries=0)
        except Exception as e:
            logger.warning("下一步建议 LLM 调用失败，降级到规则引擎: %s", e)
            raw = None

    # 6) 解析 / 降级
    if not raw:
        recs = _rule_recommendations(snap, scope)
        result = {
            "success": True,
            "mode": "rule_based",
            "message": "已基于规则引擎生成覆盖 PMI 全维度的建议（AI 大模型暂不可用）",
            "scope": scope,
            "project_name": snap.get("project_name", ""),
            "overall_assessment": _rule_overall(snap, scope),
            "health_score": health_score,
            "dimensions": dimensions,
            "recommendations": recs,
            "frameworks_used": ["PMP", "ACP", "CPMAI"],
            "kb_used": kb_ids,
        }
        _set_cache(ck, result)
        return result

    parsed = _safe_json(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("recommendations"), list):
        # 非 JSON：整段作为总体研判，回退规则建议
        recs = _rule_recommendations(snap, scope)
        result = {
            "success": True,
            "mode": "free_text",
            "message": "大模型返回为非结构化文本，已结合规则建议展示",
            "scope": scope,
            "project_name": snap.get("project_name", ""),
            "overall_assessment": raw[:600],
            "health_score": health_score,
            "dimensions": dimensions,
            "recommendations": recs,
            "frameworks_used": ["PMP", "ACP", "CPMAI"],
            "kb_used": kb_ids,
        }
        _set_cache(ck, result)
        return result

    # 用模型维度（若有）覆盖规则维度，否则保留规则维度
    model_dims = parsed.get("dimensions")
    if isinstance(model_dims, list) and model_dims:
        dimensions = [
            {
                "name": d.get("name", "未知维度"),
                "framework": d.get("framework", "PMP"),
                "status": d.get("status", "需关注"),
                "score": max(0, min(10, int(d.get("score", 5)))),
            }
            for d in model_dims
        ]
        health_score = sum(d["score"] for d in dimensions)

    recs = []
    for r in parsed.get("recommendations", []):
        if not isinstance(r, dict) or not r.get("title"):
            continue
        recs.append({
            "dimension": r.get("dimension", "整合管理"),
            "framework": r.get("framework", "PMP"),
            "priority": r.get("priority", "中"),
            "title": str(r.get("title", "")),
            "rationale": str(r.get("rationale", "")),
            "actions": list(r.get("actions", [])) if isinstance(r.get("actions"), list) else [],
            "expected_outcome": str(r.get("expected_outcome", "")),
        })

    # 模型未给建议时回退规则
    if not recs:
        recs = _rule_recommendations(snap, scope)

    result = {
        "success": True,
        "mode": "ai_generated",
        "scope": scope,
        "project_name": snap.get("project_name", ""),
        "overall_assessment": str(parsed.get("overall_assessment", "")),
        "health_score": health_score,
        "dimensions": dimensions,
        "recommendations": recs,
        "frameworks_used": parsed.get("frameworks_used", ["PMP", "ACP", "CPMAI"]),
        "kb_used": kb_ids,
    }
    _set_cache(ck, result)
    return result


def _rule_overall(snap: Dict[str, Any], scope: str) -> str:
    if scope == "project":
        return (f"「{snap.get('project_name','项目')}」平均进度 {snap.get('avg_progress')}%，"
                f"逾期 {snap.get('overdue')} 项，活跃风险 {snap.get('risk_active')} 条，"
                f"CPI={snap.get('cpi')}。建议优先处理高优先级维度。")
    return (f"组合视角共 {snap.get('task_total')} 项任务，已完成 {snap.get('task_done')} 项，"
            f"逾期 {snap.get('overdue')} 项，活跃风险 {snap.get('risk_active')} 条。"
            f"建议聚焦进度与成本偏离最大的项目。")

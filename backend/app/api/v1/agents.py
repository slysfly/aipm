"""
PMI中国AI项目管理社区 - AI Agent 能力目录 API

- 返回领域 Agent 能力清单与实时状态；
- tasksCompleted 现在基于 AgentSession 真实调用计数（而非画像值）；

[PMBOK KA: 跨领域 | PG: 执行 (Cross-area/Executing) — AI Agent目录、流程审计]
对应PMI第6版标准：AI Agent管理、流程审计

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: AI Management — AI Agent服务目录]
PMBOK 7th Principle: Team/Systems Thinking | Domain: Team — AI Agent团队、系统思考
PMBOK 8th: AI Agent Ecosystem"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.system_llm_config import SystemLLMConfig
from app.models import User, AgentSession, Project, Risk, Resource, Task, TaskStatus
from app.models.budget import ProjectBudget
from app.core.security import get_current_user
from app.services.ai.out_of_box_agents import run_agent, AGENT_INPUT_HINT

logger = logging.getLogger(__name__)
router = APIRouter(tags=["AI Agent 能力目录"])


AGENT_CATALOG: List[Dict[str, Any]] = [
    {"id": "evm", "name": "EVM 分析 Agent", "type": "analysis", "icon": "BarChartOutlined", "color": "#4F46E5",
     "description": "实时计算 PV/EV/AC/CPI/SPI 等挣值指标，自动识别成本与进度偏差", "accuracy": 97},
    {"id": "risk", "name": "风险检测 Agent", "type": "risk", "icon": "WarningOutlined", "color": "#EF4444",
     "description": "扫描逾期/低进度/临近截止任务，生成概率×影响矩阵，推荐应对策略", "accuracy": 93},
    {"id": "report", "name": "报告生成 Agent", "type": "report", "icon": "FileTextOutlined", "color": "#10B981",
     "description": "基于真实任务/风险/复盘统计自动生成日报/周报/项目状态报告", "accuracy": 99},
    {"id": "resource", "name": "资源优化 Agent", "type": "resource", "icon": "RobotOutlined", "color": "#F59E0B",
     "description": "分析资源负载热力，建议跨项目资源调配方案", "accuracy": 91},
    {"id": "wbs", "name": "WBS 生成 Agent", "type": "planning", "icon": "ThunderboltOutlined", "color": "#8B5CF6",
     "description": "AI 自动生成多级 WBS 分解并落库任务", "accuracy": 95},
    {"id": "quality", "name": "质量检测 Agent", "type": "quality", "icon": "SafetyOutlined", "color": "#06B6D4",
     "description": "分析测试/缺陷趋势，提出质量门禁建议", "accuracy": 89},
    {"id": "compliance", "name": "合规审计 Agent", "type": "compliance", "icon": "AimOutlined", "color": "#6366F1",
     "description": "按五大过程组审计项目流程合规性", "accuracy": 96},
    {"id": "meeting_minutes", "name": "纪要转任务 Agent", "type": "meeting", "icon": "FileDoneOutlined", "color": "#0EA5E9",
     "description": "解析会议纪要/需求文档，自动提取行动项并创建任务", "accuracy": 94},
    {"id": "health_check", "name": "项目健康检查 Agent", "type": "analysis", "icon": "HeartOutlined", "color": "#F43F5E",
     "description": "综合检查项目的进度/成本/风险/质量状态，输出健康评分（0-100）", "accuracy": 92},
    {"id": "decision", "name": "智能决策建议 Agent", "type": "analysis", "icon": "BulbOutlined", "color": "#8B5CF6",
     "description": "基于项目当前状态，给出3-5条可执行的决策建议", "accuracy": 90},
]


# --------------------------------------------------------------------------- #
# 真实遥测
# --------------------------------------------------------------------------- #
async def _compute_telemetry(db: AsyncSession) -> Dict[str, Dict[str, Any]]:
    sessions = (await db.execute(select(AgentSession))).scalars().all()
    counts: Dict[str, int] = {a["id"]: 0 for a in AGENT_CATALOG}
    last_active: Dict[str, Any] = {a["id"]: None for a in AGENT_CATALOG}
    for s in sessions:
        title = s.title or ""
        if title.startswith("["):
            end = title.find("]")
            tag = title[1:end] if end > 0 else ""
            if tag in counts:
                counts[tag] += 1
                if s.updated_at and (last_active[tag] is None or s.updated_at > last_active[tag]):
                    last_active[tag] = s.updated_at

    # 各 Agent 关联业务域真实记录数
    coverage = {
        "evm": (await db.execute(select(func.count(ProjectBudget.id)))).scalar() or 0,
        "risk": (await db.execute(select(func.count(Risk.id)))).scalar() or 0,
        "report": (await db.execute(select(func.count(Project.id)).where(Project.is_deleted.is_(False)))).scalar() or 0,
        "resource": (await db.execute(select(func.count(Resource.id)).where(Resource.is_active.is_(True)))).scalar() or 0,
        "wbs": (await db.execute(select(func.count(Task.id)).where(Task.parent_task_id.is_(None), Task.is_deleted.is_(False)))).scalar() or 0,
        "quality": (await db.execute(select(func.count(Task.id)).where(Task.status == TaskStatus.TESTING.value, Task.is_deleted.is_(False)))).scalar() or 0,
        "compliance": 0,
        "meeting_minutes": (await db.execute(select(func.count(Task.id)).where(Task.category == "meeting_action", Task.is_deleted.is_(False)))).scalar() or 0,
    }
    return {"counts": counts, "last_active": last_active, "coverage": coverage}


def _compute_status(llm_active: bool, team_running: bool) -> str:
    if team_running:
        return "busy"
    if llm_active:
        return "online"
    return "offline"


@router.get("/agents")
async def list_agents(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    cfg = (await db.execute(select(SystemLLMConfig).order_by(SystemLLMConfig.updated_at.desc()))).scalars().first()
    llm_active = bool(cfg and cfg.is_active and getattr(cfg, "_api_key", None))
    team_running = False  # 多智能体编排已下线，不再有团队运行中

    tele = await _compute_telemetry(db)

    agents = []
    for a in AGENT_CATALOG:
        status = _compute_status(llm_active, team_running)
        la = tele["last_active"].get(a["id"])
        agents.append({
            "id": a["id"], "name": a["name"], "type": a["type"], "icon": a["icon"], "color": a["color"],
            "description": a["description"], "status": status,
            "tasksCompleted": tele["counts"].get(a["id"], 0),
            "coverage": tele["coverage"].get(a["id"], 0),
            "accuracy": a["accuracy"],
            "lastActive": la.isoformat() if la else "待命",
            "inputHint": AGENT_INPUT_HINT.get(a["id"], ""),
        })
    return {"items": agents, "total": len(agents)}


# --------------------------------------------------------------------------- #
# 运行 Agent
# --------------------------------------------------------------------------- #
class AgentRunRequest(BaseModel):
    agent_type: str
    project_id: Optional[str] = None
    input: str = ""
    options: Dict[str, Any] = {}


@router.post("/agents/run")
async def run_agent_endpoint(
    req: AgentRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await asyncio.wait_for(
            run_agent(
                agent_type=req.agent_type,
                db=db, user_id=current_user.id,
                project_id=req.project_id, input_text=req.input, options=req.options,
            ),
            timeout=175,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"AI 服务不可用: {str(e)}")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Agent 执行超时，请稍后重试")
    except Exception as e:
        logger.exception("run_agent_endpoint 未预期异常")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")
    return {"success": True, "agent_type": req.agent_type, "result": result}


@router.get("/agents/runs")
async def list_agent_runs(
    agent_type: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = select(AgentSession)
    if agent_type:
        query = query.where(AgentSession.title.like(f"[{agent_type}]%"))
    query = query.order_by(desc(AgentSession.updated_at)).limit(limit)
    rows = (await db.execute(query)).scalars().all()
    items = []
    for s in rows:
        tag = ""
        if s.title and s.title.startswith("["):
            end = s.title.find("]")
            tag = s.title[1:end] if end > 0 else ""
        items.append({
            "id": s.id, "agent_type": tag, "summary": s.title,
            "project_id": s.project_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })
    return {"items": items, "total": len(items)}

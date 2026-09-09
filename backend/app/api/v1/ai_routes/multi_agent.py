"""
PMI中国AI项目管理社区 - 多智能体协作路由
包含多智能体团队管理、可视化编排工作流
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Task, Project, User, AgentSession, TaskStatus, TaskPriority
from app.core.security import get_current_active_user, get_current_user
from app.core.ai_engine import ai_engine
from app.services.ai.multi_agent import multi_agent_manager, MultiAgentTeam

router = APIRouter()


# =========================== multi_agent.py 路由 =========================== #


class CreateTeamRequest(BaseModel):
    """创建团队请求"""
    planner_name: str = Field(default="Planner", description="规划者Agent名称")
    executor_name: str = Field(default="Executor", description="执行者Agent名称")
    reviewer_name: str = Field(default="Reviewer", description="审查者Agent名称")
    llm_provider: Optional[str] = Field(default=None, description="LLM提供商")


class CreateTeamResponse(BaseModel):
    """创建团队响应"""
    team_id: str
    status: str
    agents: List[Dict[str, Any]]
    message: str = "团队创建成功"


class RunTeamRequest(BaseModel):
    """运行团队请求"""
    objective: str = Field(..., description="要完成的任务目标")
    context: Dict[str, Any] = Field(default_factory=dict, description="额外上下文")


class RunTeamResponse(BaseModel):
    """运行团队响应"""
    team_id: str
    objective: str
    status: str
    subtasks: List[Dict[str, Any]]
    review: Dict[str, Any]
    execution_time: float


class TeamStatusResponse(BaseModel):
    """团队状态响应"""
    team_id: str
    status: str
    objective: str
    subtask_count: int
    completed_count: int
    created_at: str
    completed_at: Optional[str]


class TeamLogResponse(BaseModel):
    """团队日志响应"""
    team_id: str
    logs: List[Dict[str, Any]]


class TeamListResponse(BaseModel):
    """团队列表响应"""
    teams: List[Dict[str, Any]]
    total: int


@router.post("/multi-agent/teams", response_model=CreateTeamResponse, dependencies=[Depends(get_current_active_user)])
async def create_team(request: CreateTeamRequest):
    """
    创建Agent团队
    
    创建一个包含Planner、Executor、Reviewer的多智能体团队
    """
    try:
        team = multi_agent_manager.create_team(llm_provider=request.llm_provider)
        team.create_team(
            planner_name=request.planner_name,
            executor_name=request.executor_name,
            reviewer_name=request.reviewer_name,
        )

        return CreateTeamResponse(
            team_id=team.team_id,
            status="created",
            agents=team.coordinator.list_agents(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建团队失败: {str(e)}")


@router.post("/multi-agent/teams/{team_id}/run", response_model=RunTeamResponse, dependencies=[Depends(get_current_active_user)])
async def run_team(team_id: str, request: RunTeamRequest):
    """
    运行团队执行任务
    
    让团队协作完成指定的目标
    """
    team = multi_agent_manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    try:
        result = await team.run(request.objective, request.context)

        return RunTeamResponse(
            team_id=result["team_id"],
            objective=result["objective"],
            status=result["status"],
            subtasks=result.get("subtasks", []),
            review=result.get("review", {}),
            execution_time=result.get("execution_time", 0),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"团队执行失败: {str(e)}")


@router.get("/multi-agent/teams/{team_id}/status", response_model=TeamStatusResponse, dependencies=[Depends(get_current_active_user)])
async def get_team_status(team_id: str):
    """
    查看团队运行状态
    """
    team = multi_agent_manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    status = team.get_status()
    return TeamStatusResponse(
        team_id=status["team_id"],
        status=status["status"],
        objective=status["objective"],
        subtask_count=status["subtask_count"],
        completed_count=status["completed_count"],
        created_at=status["created_at"],
        completed_at=status.get("completed_at"),
    )


@router.get("/multi-agent/teams/{team_id}/logs", response_model=TeamLogResponse, dependencies=[Depends(get_current_active_user)])
async def get_team_logs(team_id: str):
    """
    查看团队执行日志
    
    获取Agent间的通信记录和执行过程日志
    """
    team = multi_agent_manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    logs = team.get_logs()
    return TeamLogResponse(
        team_id=team_id,
        logs=logs,
    )


@router.get("/multi-agent/teams", response_model=TeamListResponse, dependencies=[Depends(get_current_active_user)])
async def list_teams():
    """
    列出所有团队
    """
    teams = multi_agent_manager.list_teams()
    return TeamListResponse(
        teams=teams,
        total=len(teams),
    )


@router.delete("/multi-agent/teams/{team_id}", dependencies=[Depends(get_current_active_user)])
async def delete_team(team_id: str):
    """
    删除团队
    """
    team = multi_agent_manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    multi_agent_manager.delete_team(team_id)
    return {"success": True, "message": "团队已删除"}


@router.get("/multi-agent/teams/{team_id}/agents", dependencies=[Depends(get_current_active_user)])
async def get_team_agents(team_id: str):
    """
    获取团队的Agent列表
    """
    team = multi_agent_manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    return {
        "team_id": team_id,
        "agents": team.coordinator.list_agents(),
    }


# =========================== agent_workflow.py 路由 =========================== #


class WorkflowRunRequest(BaseModel):
    objective: str
    project_id: Optional[str] = None
    create_tasks: bool = True


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


async def _llm(prompt: str, temperature: float = 0.3, max_tokens: int = 1500) -> Optional[str]:
    try:
        return await ai_engine.generate(prompt, provider=None, temperature=temperature, max_tokens=max_tokens)
    except Exception:
        return None


async def _create_task(db: AsyncSession, project_id: str, name: str, description: str = "") -> Task:
    cnt = (await db.execute(
        select(func.count(Task.id)).where(Task.project_id == project_id, Task.parent_task_id == None, Task.is_deleted == False)
    )).scalar() or 0
    task = Task(
        project_id=project_id, wbs_code=str(cnt + 1), name=name[:255],
        status=TaskStatus.TODO.value, priority=TaskPriority.MEDIUM.value,
        description=description, category="agent_workflow", labels=["multi-agent"],
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


@router.post("/multi-agent/workflow/run")
async def run_workflow(
    req: WorkflowRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """运行多智能体编排工作流（Planner -> Executor -> Reviewer）"""
    if not req.objective or not req.objective.strip():
        raise HTTPException(status_code=400, detail="目标不能为空")

    # 1) Planner 规划
    planner_raw = await _llm(
        f"你是项目规划智能体(Planner)。针对目标：{req.objective}\n"
        "生成执行计划，严格按 JSON 数组返回，每项含：step(步骤名)、owner(负责角色)、"
        "desc(说明)。最多6步，不要解释。", temperature=0.4,
    )
    plan = _safe_json(planner_raw)
    if not isinstance(plan, list) or not plan:
        plan = [{"step": req.objective, "owner": "Executor", "desc": req.objective}]

    # 2) Executor 执行（落库任务）
    created: List[Dict[str, Any]] = []
    if req.project_id and req.create_tasks:
        proj = await db.get(Project, req.project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="项目不存在")
        for i, step in enumerate(plan[:6]):
            name = str(step.get("step") or step.get("desc") or f"步骤{i+1}").strip()
            t = await _create_task(db, req.project_id, name, description=step.get("desc", ""))
            created.append({"id": t.id, "name": t.name})

    # 3) Reviewer 审查
    reviewer_raw = await _llm(
        f"你是质量审查智能体(Reviewer)。请审查以下执行计划与已创建任务，"
        f"用中文给出最多3条改进建议（不要解释、不加标题）：\n计划：{json.dumps(plan, ensure_ascii=False)}\n"
        f"已建任务：{json.dumps(created, ensure_ascii=False)}", temperature=0.3,
    )
    review = reviewer_raw or "（未配置大模型）计划结构合理，建议补充验收标准与明确负责人。"

    # 轨迹落库
    session = AgentSession(
        user_id=current_user.id, project_id=req.project_id,
        title=f"[workflow] {req.objective[:40]}",
        messages=[{"role": "system", "content": "agent_workflow", "plan": plan, "review": review}],
    )
    db.add(session)
    await db.commit()

    return {
        "success": True,
        "objective": req.objective,
        "planner": plan,
        "created_tasks": created,
        "created_count": len(created),
        "reviewer": review,
    }

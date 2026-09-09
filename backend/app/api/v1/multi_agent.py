"""
PMI中国AI项目管理社区 - 多智能体协作API路由
提供多智能体团队管理接口

[PMBOK KA: 跨领域 | PG: 执行 (Cross-area/Executing) — 多Agent协同编排]
对应PMI第6版标准：多Agent协同

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: CPMAI Methodology — 多Agent编排]
PMBOK 7th Principle: Complexity/Adaptability | Domain: Uncertainty — 驾驭复杂性、多Agent协同
PMBOK 8th: Multi-Agent Orchestration"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from app.core.security import get_current_active_user
from pydantic import BaseModel, Field

from app.services.ai.multi_agent import multi_agent_manager, MultiAgentTeam

router = APIRouter(prefix="/multi-agent", tags=["多智能体"], dependencies=[Depends(get_current_active_user)])


# ============ Pydantic 请求/响应模型 ============

class CreateTeamRequest(BaseModel):
    planner_name: str = Field(default="Planner", description="规划者Agent名称")
    executor_name: str = Field(default="Executor", description="执行者Agent名称")
    reviewer_name: str = Field(default="Reviewer", description="审查者Agent名称")
    llm_provider: Optional[str] = Field(default=None, description="LLM提供商")


class CreateTeamResponse(BaseModel):
    team_id: str
    status: str
    agents: List[Dict[str, Any]]
    message: str = "团队创建成功"


class RunTeamRequest(BaseModel):
    objective: str = Field(..., description="要完成的任务目标")
    context: Dict[str, Any] = Field(default_factory=dict, description="额外上下文")


class RunTeamResponse(BaseModel):
    team_id: str
    objective: str
    status: str
    subtasks: List[Dict[str, Any]]
    review: Dict[str, Any]
    execution_time: float


class TeamStatusResponse(BaseModel):
    team_id: str
    status: str
    objective: str
    subtask_count: int
    completed_count: int
    created_at: str
    completed_at: Optional[str]


class TeamLogResponse(BaseModel):
    team_id: str
    logs: List[Dict[str, Any]]


class TeamListResponse(BaseModel):
    teams: List[Dict[str, Any]]
    total: int


# ============ API 端点 ============

@router.post("/teams", response_model=CreateTeamResponse)
async def create_team(request: CreateTeamRequest):
    """创建Agent团队
    
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


@router.post("/teams/{team_id}/run", response_model=RunTeamResponse)
async def run_team(team_id: str, request: RunTeamRequest):
    """运行团队执行任务
    
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


@router.get("/teams/{team_id}/status", response_model=TeamStatusResponse)
async def get_team_status(team_id: str):
    """查看团队运行状态"""
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


@router.get("/teams/{team_id}/logs", response_model=TeamLogResponse)
async def get_team_logs(team_id: str):
    """查看团队执行日志
    
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


@router.get("/teams", response_model=TeamListResponse)
async def list_teams():
    列出所有团队
    teams = multi_agent_manager.list_teams()
    return TeamListResponse(
        teams=teams,
        total=len(teams),
    )


@router.delete("/teams/{team_id}")
async def delete_team(team_id: str):
    删除团队
    team = multi_agent_manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    multi_agent_manager.delete_team(team_id)
    return {"success": True, "message": "团队已删除"}


@router.get("/teams/{team_id}/agents")
async def get_team_agents(team_id: str):
    获取团队的Agent列表
    team = multi_agent_manager.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    return {
        "team_id": team_id,
        "agents": team.coordinator.list_agents(),
    }

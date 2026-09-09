"""
PMI中国AI项目管理社区 - 多智能体编排器
管理Agent生命周期，调度Agent执行顺序，处理Agent间通信
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from .helpers import (
    AgentRole, AgentStatus, TaskStatus,
    AgentPlan, AgentResult, AgentLog, SubTask,
    BaseAgent,
)
from .agents import PlannerAgent, ExecutorAgent, ReviewerAgent


class Coordinator:
    """
    协调器
    管理Agent生命周期，调度Agent执行顺序，处理Agent间通信
    """

    def __init__(self):
        from app.core.mcp_server import mcp_server

        self._agents: Dict[str, BaseAgent] = {}
        self._message_queue = mcp_server.message_queue
        self._execution_logs: List[AgentLog] = []
        self._running = False

    def register_agent(self, agent: BaseAgent):
        """注册Agent"""
        self._agents[agent.name] = agent
        self._message_queue.register_agent(agent.name)

    def unregister_agent(self, agent_name: str):
        """注销Agent"""
        if agent_name in self._agents:
            del self._agents[agent_name]

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """获取Agent"""
        return self._agents.get(name)

    def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有Agent"""
        return [agent.to_dict() for agent in self._agents.values()]

    async def execute_sequence(
        self,
        steps: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> List[AgentResult]:
        """
        按顺序执行步骤
        """
        results = []
        for step in steps:
            agent_name = step.get("agent", "Executor")
            agent = self.get_agent(agent_name)

            if not agent:
                results.append(AgentResult(success=False, message=f"Agent {agent_name} not found"))
                continue

            # 更新上下文
            step_context = {**context, **step.get("context", {})}

            # 执行
            plan = await agent.think(step_context)
            result = await agent.execute(plan)
            results.append(result)

            # 收集日志
            self._execution_logs.extend(agent.get_logs())

        return results

    async def execute_parallel(
        self,
        steps: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> List[AgentResult]:
        """
        并行执行步骤
        """
        import asyncio

        tasks = []
        for step in steps:
            agent_name = step.get("agent", "Executor")
            agent = self.get_agent(agent_name)

            if not agent:
                continue

            step_context = {**context, **step.get("context", {})}
            plan = await agent.think(step_context)
            tasks.append(agent.execute(plan))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 收集日志
        for step in steps:
            agent = self.get_agent(step.get("agent", "Executor"))
            if agent:
                self._execution_logs.extend(agent.get_logs())

        return [
            r if isinstance(r, AgentResult) else AgentResult(success=False, message=str(r))
            for r in results
        ]

    def get_logs(self) -> List[AgentLog]:
        """获取所有执行日志"""
        return self._execution_logs.copy()

    def clear_logs(self):
        """清空日志"""
        self._execution_logs.clear()


class MultiAgentTeam:
    """
    多智能体团队
    创建团队（Planner + Executor + Reviewer），运行团队协作完成目标
    """

    def __init__(self, team_id: Optional[str] = None, llm_provider: Optional[str] = None):
        self.team_id = team_id or str(uuid.uuid4())
        self.llm_provider = llm_provider
        self.coordinator = Coordinator()
        self.planner: Optional[PlannerAgent] = None
        self.executor: Optional[ExecutorAgent] = None
        self.reviewer: Optional[ReviewerAgent] = None
        self._subtasks: List[SubTask] = []
        self._results: List[AgentResult] = []
        self._status = TaskStatus.PENDING
        self._objective = ""
        self._created_at = datetime.now()
        self._completed_at: Optional[datetime] = None

    def create_team(
        self,
        planner_name: str = "Planner",
        executor_name: str = "Executor",
        reviewer_name: str = "Reviewer",
    ):
        """创建Agent团队"""
        self.planner = PlannerAgent(llm_provider=self.llm_provider)
        self.planner.name = planner_name

        self.executor = ExecutorAgent(llm_provider=self.llm_provider)
        self.executor.name = executor_name

        self.reviewer = ReviewerAgent(llm_provider=self.llm_provider)
        self.reviewer.name = reviewer_name

        # 注册到协调器
        self.coordinator.register_agent(self.planner)
        self.coordinator.register_agent(self.executor)
        self.coordinator.register_agent(self.reviewer)

    def add_custom_agent(self, agent: BaseAgent):
        """添加自定义Agent"""
        self.coordinator.register_agent(agent)

    async def run(self, objective: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        运行团队协作完成目标
        完整流程：规划 -> 执行 -> 审查
        """
        self._objective = objective
        self._status = TaskStatus.IN_PROGRESS
        self._results = []

        if not self.planner or not self.executor or not self.reviewer:
            raise RuntimeError("Team not created. Call create_team() first.")

        try:
            # Step 1: Planner 分解目标
            available_agents = [
                self.executor.to_dict(),
                self.reviewer.to_dict(),
            ]
            self._subtasks = await self.planner.decompose_objective(objective, available_agents)

            # Step 2: Executor 执行子任务
            for subtask in self._subtasks:
                subtask.status = TaskStatus.IN_PROGRESS

                step_context = {
                    "task": subtask.description,
                    "objective": objective,
                    **(context or {}),
                }

                plan = await self.executor.think(step_context)
                result = await self.executor.execute(plan)

                subtask.result = result
                subtask.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
                subtask.completed_at = datetime.now()
                self._results.append(result)

            # Step 3: Reviewer 审查结果
            combined_result = AgentResult(
                success=all(r.success for r in self._results),
                data={"subtask_results": [r.data for r in self._results]},
                message="All subtasks completed" if all(r.success for r in self._results) else "Some subtasks failed",
            )

            review_criteria = [
                "结果是否完整覆盖了目标",
                "执行过程是否有错误",
                "输出质量是否符合要求",
            ]
            review_report = await self.reviewer.review(combined_result, review_criteria)

            self._status = TaskStatus.REVIEWING

            # 根据审查结果决定是否需要重新执行
            if not review_report.get("passed", True):
                # 可以在这里实现重新执行逻辑
                pass

            self._status = TaskStatus.COMPLETED
            self._completed_at = datetime.now()

            return {
                "team_id": self.team_id,
                "objective": objective,
                "status": self._status.value,
                "subtasks": [
                    {
                        "id": st.id,
                        "description": st.description,
                        "assigned_to": st.assigned_to,
                        "status": st.status.value,
                        "result": {
                            "success": st.result.success if st.result else False,
                            "message": st.result.message if st.result else "",
                        } if st.result else None,
                    }
                    for st in self._subtasks
                ],
                "review": review_report,
                "execution_time": (self._completed_at - self._created_at).total_seconds() if self._completed_at else 0,
            }

        except Exception as e:
            self._status = TaskStatus.FAILED
            return {
                "team_id": self.team_id,
                "objective": objective,
                "status": self._status.value,
                "error": str(e),
            }

    def get_status(self) -> Dict[str, Any]:
        """获取团队运行状态"""
        return {
            "team_id": self.team_id,
            "status": self._status.value,
            "objective": self._objective,
            "subtask_count": len(self._subtasks),
            "completed_count": sum(1 for st in self._subtasks if st.status == TaskStatus.COMPLETED),
            "created_at": self._created_at.isoformat(),
            "completed_at": self._completed_at.isoformat() if self._completed_at else None,
        }

    def get_logs(self) -> List[Dict[str, Any]]:
        """获取所有执行日志"""
        from .agents.report_agent import ReportAgent

        logs = []
        if self.planner:
            logs.extend(self.planner.get_logs())
        if self.executor:
            logs.extend(self.executor.get_logs())
        if self.reviewer:
            logs.extend(self.reviewer.get_logs())
        logs.extend(self.coordinator.get_logs())
        return ReportAgent.format_logs(logs)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "team_id": self.team_id,
            "status": self._status.value,
            "objective": self._objective,
            "agents": self.coordinator.list_agents(),
            "subtask_count": len(self._subtasks),
            "created_at": self._created_at.isoformat(),
        }


# ============ 全局管理器 ============

class MultiAgentManager:
    """多智能体团队管理器"""

    def __init__(self):
        self._teams: Dict[str, MultiAgentTeam] = {}

    def create_team(self, llm_provider: Optional[str] = None) -> MultiAgentTeam:
        """创建新团队"""
        team = MultiAgentTeam(llm_provider=llm_provider)
        team.create_team()
        self._teams[team.team_id] = team
        return team

    def get_team(self, team_id: str) -> Optional[MultiAgentTeam]:
        """获取团队"""
        return self._teams.get(team_id)

    def list_teams(self) -> List[Dict[str, Any]]:
        """列出所有团队"""
        return [team.to_dict() for team in self._teams.values()]

    def delete_team(self, team_id: str):
        """删除团队"""
        if team_id in self._teams:
            del self._teams[team_id]


# 全局管理器实例
multi_agent_manager = MultiAgentManager()

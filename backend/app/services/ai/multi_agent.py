"""
PMI中国AI项目管理社区 - 多智能体协作框架
支持Planner、Executor、Reviewer等Agent角色协作
"""

import json
import uuid
import asyncio
from typing import Dict, Any, List, Optional, Callable, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod

from app.core.ai_engine import ai_engine
from app.core.mcp_server import mcp_server, MCPMessage
from app.config import settings


class AgentRole(Enum):
    """Agent角色枚举"""
    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    COORDINATOR = "coordinator"
    CUSTOM = "custom"


class AgentStatus(Enum):
    """Agent状态枚举"""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    COMMUNICATING = "communicating"
    COMPLETED = "completed"
    ERROR = "error"


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEWING = "reviewing"


@dataclass
class AgentPlan:
    """Agent计划"""
    steps: List[Dict[str, Any]]
    reasoning: str = ""
    estimated_duration: int = 0
    dependencies: List[str] = field(default_factory=list)


@dataclass
class AgentResult:
    """Agent执行结果"""
    success: bool
    data: Any = None
    message: str = ""
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentLog:
    """Agent执行日志"""
    id: str
    agent_name: str
    action: str
    content: str
    timestamp: datetime
    level: str = "info"


@dataclass
class SubTask:
    """子任务"""
    id: str
    description: str
    assigned_to: str
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[AgentResult] = None
    dependencies: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class BaseAgent(ABC):
    """
    Agent基类
    所有Agent角色的抽象基类
    """

    def __init__(
        self,
        name: str,
        role: AgentRole,
        description: str,
        tools: List[str],
        llm_provider: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())
        self.name = name
        self.role = role
        self.description = description
        self.tools = tools
        self.llm_provider = llm_provider or settings.LLM_MODEL
        self.status = AgentStatus.IDLE
        self._message_queue = mcp_server.message_queue
        self._logs: List[AgentLog] = []

    def _log(self, action: str, content: str, level: str = "info"):
        """记录日志"""
        log = AgentLog(
            id=str(uuid.uuid4()),
            agent_name=self.name,
            action=action,
            content=content,
            timestamp=datetime.now(),
            level=level,
        )
        self._logs.append(log)

    def get_logs(self) -> List[AgentLog]:
        """获取日志"""
        return self._logs.copy()

    async def think(self, context: Dict[str, Any]) -> AgentPlan:
        """
        思考并制定计划
        使用LLM分析上下文并生成执行计划
        """
        self.status = AgentStatus.THINKING
        self._log("think", f"开始思考，上下文: {json.dumps(context, ensure_ascii=False, default=str)[:200]}")

        prompt = self._build_think_prompt(context)

        try:
            response = await ai_engine.generate(
                prompt,
                provider=self.llm_provider,
                temperature=0.3,
                max_tokens=2000,
            )
            plan = self._parse_plan(response)
            self._log("think", f"计划生成完成，共 {len(plan.steps)} 个步骤")
            self.status = AgentStatus.IDLE
            return plan
        except Exception as e:
            self._log("think", f"思考失败: {str(e)}", level="error")
            self.status = AgentStatus.ERROR
            return AgentPlan(steps=[], reasoning=f"Error: {str(e)}")

    async def execute(self, plan: AgentPlan) -> AgentResult:
        """
        执行计划
        根据计划步骤逐步执行
        """
        self.status = AgentStatus.EXECUTING
        start_time = datetime.now()
        self._log("execute", f"开始执行计划，共 {len(plan.steps)} 个步骤")

        results = []
        for i, step in enumerate(plan.steps):
            try:
                self._log("execute", f"执行步骤 {i+1}/{len(plan.steps)}: {step.get('action', 'unknown')}")
                result = await self._execute_step(step)
                results.append(result)
                if not result.success:
                    break
            except Exception as e:
                self._log("execute", f"步骤 {i+1} 执行失败: {str(e)}", level="error")
                results.append(AgentResult(success=False, message=str(e)))
                break

        execution_time = (datetime.now() - start_time).total_seconds()
        success = all(r.success for r in results)

        self.status = AgentStatus.COMPLETED if success else AgentStatus.ERROR
        self._log("execute", f"计划执行完成，成功: {success}")

        return AgentResult(
            success=success,
            data={"results": results},
            message="执行完成" if success else "部分步骤执行失败",
            execution_time=execution_time,
        )

    async def communicate(self, message: str, target_agent: str) -> str:
        """
        与其他Agent通信
        通过消息队列发送和接收消息
        """
        self.status = AgentStatus.COMMUNICATING
        msg_id = str(uuid.uuid4())

        mcp_msg = MCPMessage(
            id=msg_id,
            sender=self.name,
            receiver=target_agent,
            content=message,
            message_type="agent_communication",
        )

        self._log("communicate", f"发送消息给 {target_agent}: {message[:100]}")
        await self._message_queue.send(mcp_msg)

        # 等待响应
        response = await self._message_queue.receive(self.name, timeout=30.0)
        self.status = AgentStatus.IDLE

        if response:
            self._log("communicate", f"收到 {response.sender} 的响应")
            return response.content
        return ""

    @abstractmethod
    def _build_think_prompt(self, context: Dict[str, Any]) -> str:
        """构建思考提示词"""
        pass

    @abstractmethod
    def _parse_plan(self, response: str) -> AgentPlan:
        """解析计划响应"""
        pass

    @abstractmethod
    async def _execute_step(self, step: Dict[str, Any]) -> AgentResult:
        """执行单个步骤"""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role.value,
            "description": self.description,
            "tools": self.tools,
            "status": self.status.value,
            "llm_provider": self.llm_provider,
        }


class PlannerAgent(BaseAgent):
    """
    规划者Agent
    接收用户目标，分解为子任务，分配给合适的执行Agent
    """

    def __init__(self, llm_provider: Optional[str] = None):
        super().__init__(
            name="Planner",
            role=AgentRole.PLANNER,
            description="负责将用户目标分解为可执行的子任务，并制定执行策略",
            tools=["analyze_project", "ai_chat"],
            llm_provider=llm_provider,
        )

    def _build_think_prompt(self, context: Dict[str, Any]) -> str:
        objective = context.get("objective", "")
        available_agents = context.get("available_agents", [])
        constraints = context.get("constraints", {})

        agents_desc = "\n".join([
            f"- {a['name']} ({a['role']}): {a['description']}"
            for a in available_agents
        ])

        return f"""你是一位项目管理规划专家。请将以下目标分解为详细的执行计划。

用户目标：{objective}

可用Agent：
{agents_desc}

约束条件：{json.dumps(constraints, ensure_ascii=False)}

请输出JSON格式的计划：
{{
    "reasoning": "分解思路",
    "steps": [
        {{
            "id": "step-1",
            "action": "具体行动描述",
            "assigned_to": "Agent名称",
            "estimated_duration": 10,
            "dependencies": [],
            "input": {{}},
            "expected_output": "预期结果"
        }}
    ],
    "estimated_duration": 30
}}

要求：
1. 每个步骤明确指定执行Agent
2. 标注步骤间的依赖关系
3. 提供预估执行时间
4. 只输出JSON，不要其他内容"""

    def _parse_plan(self, response: str) -> AgentPlan:
        try:
            data = json.loads(response.strip().strip("`").strip("json").strip("`").strip())
            return AgentPlan(
                steps=data.get("steps", []),
                reasoning=data.get("reasoning", ""),
                estimated_duration=data.get("estimated_duration", 0),
                dependencies=[],
            )
        except json.JSONDecodeError:
            # 尝试从文本中提取JSON
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    return AgentPlan(
                        steps=data.get("steps", []),
                        reasoning=data.get("reasoning", ""),
                        estimated_duration=data.get("estimated_duration", 0),
                    )
                except json.JSONDecodeError:
                    pass
            return AgentPlan(
                steps=[{"action": "direct_execution", "input": response}],
                reasoning="Failed to parse structured plan, using direct execution",
            )

    async def _execute_step(self, step: Dict[str, Any]) -> AgentResult:
        # Planner主要负责规划，不直接执行操作
        return AgentResult(
            success=True,
            data=step,
            message=f"Plan step: {step.get('action', 'unknown')}",
        )

    async def decompose_objective(self, objective: str, available_agents: List[Dict[str, Any]]) -> List[SubTask]:
        """
        将目标分解为子任务
        """
        context = {
            "objective": objective,
            "available_agents": available_agents,
        }

        plan = await self.think(context)
        subtasks = []

        for step in plan.steps:
            subtask = SubTask(
                id=step.get("id", str(uuid.uuid4())),
                description=step.get("action", ""),
                assigned_to=step.get("assigned_to", "Executor"),
                dependencies=step.get("dependencies", []),
            )
            subtasks.append(subtask)

        self._log("decompose", f"目标已分解为 {len(subtasks)} 个子任务")
        return subtasks


class ExecutorAgent(BaseAgent):
    """
    执行者Agent
    执行具体任务（创建任务、查询数据等），返回执行结果
    """

    def __init__(self, llm_provider: Optional[str] = None):
        super().__init__(
            name="Executor",
            role=AgentRole.EXECUTOR,
            description="负责执行具体的项目管理操作，如创建任务、更新状态、生成报告等",
            tools=["create_task", "query_tasks", "update_task", "generate_report", "create_project"],
            llm_provider=llm_provider,
        )

    def _build_think_prompt(self, context: Dict[str, Any]) -> str:
        task = context.get("task", "")
        available_tools = context.get("available_tools", self.tools)

        return f"""你是一位项目执行专家。请分析以下任务并确定最佳执行方案。

任务：{task}

可用工具：{', '.join(available_tools)}

请输出JSON格式的执行计划：
{{
    "reasoning": "执行思路",
    "steps": [
        {{
            "action": "工具名称或操作",
            "parameters": {{}},
            "expected_result": "预期结果"
        }}
    ]
}}

只输出JSON，不要其他内容。"""

    def _parse_plan(self, response: str) -> AgentPlan:
        try:
            data = json.loads(response.strip().strip("`").strip("json").strip("`").strip())
            return AgentPlan(
                steps=data.get("steps", []),
                reasoning=data.get("reasoning", ""),
            )
        except json.JSONDecodeError:
            return AgentPlan(
                steps=[{"action": "execute_direct", "task": response}],
                reasoning="Direct execution",
            )

    async def _execute_step(self, step: Dict[str, Any]) -> AgentResult:
        action = step.get("action", "")
        parameters = step.get("parameters", {})

        # 调用MCP工具
        if action in ["create_task", "query_tasks", "update_task", "generate_report", "create_project"]:
            try:
                result = await mcp_server.call_tool(action, parameters)
                content = result.get("content", [{}])[0].get("text", "")
                return AgentResult(
                    success=not result.get("isError", False),
                    data=json.loads(content) if content else {},
                    message=f"Tool {action} executed",
                )
            except Exception as e:
                return AgentResult(success=False, message=str(e))

        # 使用LLM直接处理
        if action in ["execute_direct", "ai_chat"]:
            try:
                task = step.get("task", parameters.get("message", ""))
                response = await ai_engine.generate(
                    f"请执行以下任务并返回结果：\n\n{task}",
                    provider=self.llm_provider,
                    temperature=0.3,
                )
                return AgentResult(success=True, data={"response": response}, message="Direct execution completed")
            except Exception as e:
                return AgentResult(success=False, message=str(e))

        return AgentResult(success=False, message=f"Unknown action: {action}")


class ReviewerAgent(BaseAgent):
    """
    审查者Agent
    审查执行结果，提出修改建议
    """

    def __init__(self, llm_provider: Optional[str] = None):
        super().__init__(
            name="Reviewer",
            role=AgentRole.REVIEWER,
            description="负责审查执行结果的质量，识别问题并提出改进建议",
            tools=["analyze_project", "ai_chat"],
            llm_provider=llm_provider,
        )

    def _build_think_prompt(self, context: Dict[str, Any]) -> str:
        result = context.get("result", {})
        criteria = context.get("criteria", [])

        return f"""你是一位质量审查专家。请审查以下执行结果。

执行结果：{json.dumps(result, ensure_ascii=False, default=str)}

审查标准：
{chr(10).join(f"- {c}" for c in criteria)}

请输出JSON格式的审查报告：
{{
    "passed": true/false,
    "score": 0.85,
    "issues": [
        {{
            "severity": "high/medium/low",
            "description": "问题描述",
            "suggestion": "改进建议"
        }}
    ],
    "recommendations": ["建议1", "建议2"]
}}

只输出JSON，不要其他内容。"""

    def _parse_plan(self, response: str) -> AgentPlan:
        return AgentPlan(steps=[{"action": "review", "content": response}])

    async def _execute_step(self, step: Dict[str, Any]) -> AgentResult:
        return AgentResult(success=True, data=step)

    async def review(self, result: AgentResult, criteria: List[str]) -> Dict[str, Any]:
        """
        审查执行结果
        """
        context = {
            "result": result.to_dict() if hasattr(result, "to_dict") else result.__dict__,
            "criteria": criteria,
        }

        plan = await self.think(context)
        review_content = plan.steps[0].get("content", "{}") if plan.steps else "{}"

        try:
            review_data = json.loads(review_content.strip().strip("`").strip("json").strip("`").strip())
        except json.JSONDecodeError:
            review_data = {
                "passed": True,
                "score": 0.8,
                "issues": [],
                "recommendations": [],
            }

        self._log("review", f"审查完成，通过: {review_data.get('passed', True)}, 评分: {review_data.get('score', 0)}")
        return review_data

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["review_criteria"] = ["准确性", "完整性", "一致性", "可执行性"]
        return data


class Coordinator:
    """
    协调器
    管理Agent生命周期，调度Agent执行顺序，处理Agent间通信
    """

    def __init__(self):
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
        logs = []
        if self.planner:
            logs.extend(self.planner.get_logs())
        if self.executor:
            logs.extend(self.executor.get_logs())
        if self.reviewer:
            logs.extend(self.reviewer.get_logs())
        logs.extend(self.coordinator.get_logs())
        return [
            {
                "id": log.id,
                "agent_name": log.agent_name,
                "action": log.action,
                "content": log.content,
                "timestamp": log.timestamp.isoformat(),
                "level": log.level,
            }
            for log in sorted(logs, key=lambda x: x.timestamp)
        ]

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

"""
PMI中国AI项目管理社区 - 多智能体框架辅助模块
包含枚举、数据类和Agent基类
"""

import json
import uuid
import asyncio
from typing import Dict, Any, List, Optional, Callable, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod


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
        from app.core.mcp_server import mcp_server
        from app.config import settings

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
        from app.core.ai_engine import ai_engine

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
        from app.core.mcp_server import MCPMessage

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

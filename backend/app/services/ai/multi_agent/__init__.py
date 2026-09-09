"""
PMI中国AI项目管理社区 - 多智能体协作框架
支持Planner、Executor、Reviewer等Agent角色协作

此文件从包中各模块重新导出所有公共符号，保持向后兼容。
"""

from .helpers import (
    AgentRole,
    AgentStatus,
    TaskStatus,
    AgentPlan,
    AgentResult,
    AgentLog,
    SubTask,
    BaseAgent,
)
from .agents import (
    PlannerAgent,
    ExecutorAgent,
    ReviewerAgent,
    ReportAgent,
)
from .orchestrator import (
    Coordinator,
    MultiAgentTeam,
    MultiAgentManager,
    multi_agent_manager,
)

__all__ = [
    # 枚举
    "AgentRole",
    "AgentStatus",
    "TaskStatus",
    # 数据类
    "AgentPlan",
    "AgentResult",
    "AgentLog",
    "SubTask",
    # Agent基类
    "BaseAgent",
    # Agent实现
    "PlannerAgent",
    "ExecutorAgent",
    "ReviewerAgent",
    "ReportAgent",
    # 编排器
    "Coordinator",
    "MultiAgentTeam",
    "MultiAgentManager",
    # 全局实例
    "multi_agent_manager",
]

from sqlalchemy import text
"""
PMI中国AI项目管理社区 - LLM 调用日志模型

记录每一次 LLM 调用的真实可观测指标：模型 / 任务 / 用户 / 项目 /
Token 用量 / 延迟 / 成本 / 状态。用于 AI 成本与性能监控面板（#3）。

[PMBOK KA: 跨领域 | PG: 监控 (Monitoring & Controlling) — AI成本绩效]
"""

from sqlalchemy import (
    Column, String, Boolean, Integer, DateTime, ForeignKey, Numeric, Text, Index,
)
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class LLMCallLog(Base):
    """LLM 调用日志模型"""

    __tablename__ = "llm_call_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)

    # 调用主体
    provider = Column(String(50), nullable=False, index=True)       # openai / minimax / deepseek ...
    model = Column(String(100), nullable=False, index=True)         # gpt-4o / abab6.5 ...
    task_name = Column(String(100), nullable=True, index=True)      # wbs / risk / evm / chat ...
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)

    # 用量（tokens，估算值，误差 <15%）
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    # 性能与成本
    latency_ms = Column(Integer, default=0)
    cost_usd = Column(Numeric(12, 6), default=0)                    # 参考成本（美元）

    # 状态
    status = Column(String(20), default="success", index=True)      # success / error
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), index=True)

    __table_args__ = (
        Index("ix_llm_provider_model", "provider", "model"),
        Index("ix_llm_created", "created_at"),
        Index("ix_llm_task", "task_name"),
    )

    def __repr__(self):
        return f"<LLMCallLog {self.provider}/{self.model} {self.status} {self.total_tokens}tk>"

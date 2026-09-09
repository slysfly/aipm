"""
PMI中国AI项目管理社区 - 审批流程模型
支持多级审批、条件分支、转交、委托
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, JSON, Index, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.session import Base
from app.models import generate_uuid


class EntityType(str, enum.Enum):
    """审批实体类型"""
    TASK = "task"
    BUDGET = "budget"
    LEAVE = "leave"
    EXPENSE = "expense"
    CHANGE_REQUEST = "change_request"


class ApprovalStatus(str, enum.Enum):
    """审批状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class StepStatus(str, enum.Enum):
    """步骤状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TRANSFERRED = "transferred"


class ApprovalFlow(Base):
    """审批流程定义"""
    __tablename__ = "approval_flows"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    entity_type = Column(String(20), nullable=False, index=True)  # task/budget/leave/expense
    steps = Column(JSON, default=list)  # [{step_order, approver_role, approver_id, condition}]
    is_active = Column(Boolean, default=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    creator = relationship("User")
    instances = relationship("ApprovalInstance", back_populates="flow", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_flow_entity_active", "entity_type", "is_active"),
    )

    def __repr__(self):
        return f"<ApprovalFlow {self.name}>"


class ApprovalInstance(Base):
    """审批实例"""
    __tablename__ = "approval_instances"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    flow_id = Column(String(36), ForeignKey("approval_flows.id"), nullable=False, index=True)
    entity_type = Column(String(20), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    requester_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default=ApprovalStatus.PENDING.value, index=True)
    current_step = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    flow = relationship("ApprovalFlow", back_populates="instances", lazy="selectin")
    requester = relationship("User", foreign_keys=[requester_id], lazy="selectin")
    steps = relationship("ApprovalStep", back_populates="instance", cascade="all, delete-orphan", order_by="ApprovalStep.step_order", lazy="selectin")

    __table_args__ = (
        Index("ix_instance_entity", "entity_type", "entity_id"),
        Index("ix_instance_requester_status", "requester_id", "status"),
    )

    def __repr__(self):
        try:
            return f"<ApprovalInstance {self.id[:8]} {self.status}>"
        except Exception:
            return "<ApprovalInstance ?(detached)>"


class ApprovalStep(Base):
    """审批步骤记录"""
    __tablename__ = "approval_steps"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    instance_id = Column(String(36), ForeignKey("approval_instances.id"), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    approver_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    original_approver_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # 转交前原审批人
    status = Column(String(20), default=StepStatus.PENDING.value, index=True)
    comment = Column(Text)
    acted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    instance = relationship("ApprovalInstance", back_populates="steps")
    approver = relationship("User", foreign_keys=[approver_id])
    original_approver = relationship("User", foreign_keys=[original_approver_id])

    __table_args__ = (
        Index("ix_step_instance_order", "instance_id", "step_order"),
        Index("ix_step_approver_status", "approver_id", "status"),
    )

    def __repr__(self):
        return f"<ApprovalStep {self.step_order} {self.status}>"


class ApprovalDelegate(Base):
    """审批委托"""
    __tablename__ = "approval_delegates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    delegator_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    delegatee_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    delegator = relationship("User", foreign_keys=[delegator_id])
    delegatee = relationship("User", foreign_keys=[delegatee_id])

    __table_args__ = (
        Index("ix_delegate_delegator", "delegator_id", "is_active"),
        Index("ix_delegate_delegatee", "delegatee_id", "is_active"),
        Index("ix_delegate_date", "start_date", "end_date"),
    )

    def __repr__(self):
        return f"<ApprovalDelegate {self.delegator_id[:8]} -> {self.delegatee_id[:8]}>"

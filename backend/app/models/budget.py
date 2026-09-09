from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 预算/成本跟踪模型
包含项目预算、预算分类和成本记录
"""

from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Enum, Text, Date, Index, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.session import Base
from app.models import generate_uuid


class CurrencyType(str, enum.Enum):
    """币种枚举"""
    CNY = "CNY"
    USD = "USD"
    EUR = "EUR"


class BudgetStatus(str, enum.Enum):
    """预算状态枚举"""
    DRAFT = "draft"
    ACTIVE = "active"
    EXCEEDED = "exceeded"
    CLOSED = "closed"


class CostType(str, enum.Enum):
    """成本类型枚举"""
    LABOR = "labor"
    MATERIAL = "material"
    OVERHEAD = "overhead"
    TRAVEL = "travel"
    OTHER = "other"


class ProjectBudget(Base):
    """项目预算模型"""
    __tablename__ = "project_budgets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    total_budget = Column(Numeric(15, 2), default=0, nullable=False)
    currency = Column(String(3), default=CurrencyType.CNY.value, nullable=False)
    labor_rate = Column(Numeric(10, 2), default=0, nullable=False)
    overhead_rate = Column(Numeric(5, 4), default=0, nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(20), default=BudgetStatus.DRAFT.value, nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    project = relationship("Project", foreign_keys=[project_id])
    creator = relationship("User", foreign_keys=[created_by])
    categories = relationship("BudgetCategory", back_populates="budget", cascade="all, delete-orphan")
    cost_records = relationship("CostRecord", back_populates="budget", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_budget_project", "project_id"),
        Index("ix_budget_status", "status"),
    )

    def __repr__(self):
        return f"<ProjectBudget {self.project_id} {self.total_budget} {self.currency}>"


class BudgetCategory(Base):
    """预算分类模型"""
    __tablename__ = "budget_categories"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    budget_id = Column(String(36), ForeignKey("project_budgets.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    allocated_amount = Column(Numeric(15, 2), default=0, nullable=False)
    spent_amount = Column(Numeric(15, 2), default=0, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    budget = relationship("ProjectBudget", back_populates="categories")
    cost_records = relationship("CostRecord", back_populates="category")

    __table_args__ = (
        Index("ix_category_budget", "budget_id"),
    )

    def __repr__(self):
        return f"<BudgetCategory {self.name} {self.allocated_amount}>"


class CostRecord(Base):
    """成本记录模型"""
    __tablename__ = "cost_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    budget_id = Column(String(36), ForeignKey("project_budgets.id"), nullable=False, index=True)
    category_id = Column(String(36), ForeignKey("budget_categories.id"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    cost_type = Column(String(20), default=CostType.OTHER.value, nullable=False)
    amount = Column(Numeric(15, 2), default=0, nullable=False)
    description = Column(Text)
    recorded_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    receipt_url = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 人工成本专用字段
    work_hours = Column(Numeric(10, 2), default=0)
    labor_rate_at_record = Column(Numeric(10, 2), default=0)

    # 关系
    project = relationship("Project", foreign_keys=[project_id])
    budget = relationship("ProjectBudget", back_populates="cost_records")
    category = relationship("BudgetCategory", back_populates="cost_records")
    task = relationship("Task", foreign_keys=[task_id])
    recorder = relationship("User", foreign_keys=[recorded_by])

    __table_args__ = (
        Index("ix_cost_project", "project_id"),
        Index("ix_cost_budget", "budget_id"),
        Index("ix_cost_category", "category_id"),
        Index("ix_cost_task", "task_id"),
        Index("ix_cost_type", "cost_type"),
        Index("ix_cost_recorded_at", "recorded_at"),
    )

    def __repr__(self):
        return f"<CostRecord {self.cost_type} {self.amount}>"

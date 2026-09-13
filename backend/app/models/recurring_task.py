from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, JSON, Integer, Index, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class RecurringTask(Base):
    """重复任务规则模型"""
    __tablename__ = "recurring_tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    base_task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)

    # 重复模式: daily/weekly/biweekly/monthly/quarterly/yearly/custom
    pattern = Column(String(20), nullable=False, default="daily")
    interval_days = Column(Integer, default=1)  # 自定义模式时每N天
    week_days = Column(JSON, default=list)  # 每周模式时选中的星期几 [1,3,5]
    month_day = Column(Integer, default=1)  # 每月模式时选中的日期 1-31

    # 结束条件: never/after_count/on_date
    end_condition = Column(String(20), default="never")
    end_after_count = Column(Integer, default=0)  # 执行N次后结束
    end_date = Column(DateTime(timezone=True))  # 指定日期结束

    # 执行记录
    next_run_at = Column(DateTime(timezone=True))
    last_run_at = Column(DateTime(timezone=True))
    run_count = Column(Integer, default=0)  # 已执行次数

    is_active = Column(Boolean, default=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    base_task = relationship("Task", foreign_keys=[base_task_id])
    project = relationship("Project")
    creator = relationship("User", foreign_keys=[created_by])
    instances = relationship("RecurringTaskInstance", back_populates="recurring_task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_recurring_task_project", "project_id", "is_active"),
        Index("ix_recurring_task_next_run", "next_run_at", "is_active"),
        Index("ix_recurring_task_pattern", "pattern", "is_active"),
    )

    def __repr__(self):
        return f"<RecurringTask {self.pattern} next={self.next_run_at}>"


class RecurringTaskInstance(Base):
    """重复任务生成的实例记录"""
    __tablename__ = "recurring_task_instances"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    recurring_task_id = Column(String(36), ForeignKey("recurring_tasks.id"), nullable=False, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)

    # 实例生成信息
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    sequence_number = Column(Integer, default=1)  # 第几次生成的实例

    # 关系
    recurring_task = relationship("RecurringTask", back_populates="instances")
    task = relationship("Task", foreign_keys=[task_id])

    __table_args__ = (
        Index("ix_recurring_instance_task", "recurring_task_id", "sequence_number"),
    )

    def __repr__(self):
        return f"<RecurringTaskInstance #{self.sequence_number} task={self.task_id}>"

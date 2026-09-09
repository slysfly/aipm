from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 定时任务模型
支持基于Cron表达式的定时任务调度
"""

import enum
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, JSON, Index, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class JobType(str, enum.Enum):
    """任务类型枚举"""
    REPORT = "report"
    NOTIFICATION = "notification"
    CLEANUP = "cleanup"
    SYNC = "sync"
    AI_ANALYSIS = "ai_analysis"


class JobStatus(str, enum.Enum):
    """任务执行状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class ScheduledJob(Base):
    """定时任务模型"""
    __tablename__ = "scheduled_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    job_type = Column(String(50), nullable=False, index=True)  # report/notification/cleanup/sync/ai_analysis
    cron_expression = Column(String(100), nullable=False)  # 标准5字段cron
    parameters = Column(JSON, default=dict)  # 任务参数
    is_active = Column(Boolean, default=True)

    # 执行记录
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True))
    run_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)  # 当前重试次数

    # 创建者
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    creator = relationship("User", foreign_keys=[created_by])
    execution_logs = relationship("JobExecutionLog", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_scheduled_job_type_active", "job_type", "is_active"),
        Index("ix_scheduled_job_next_run", "next_run_at", "is_active"),
        Index("ix_scheduled_job_created_by", "created_by", "created_at"),
    )

    def __repr__(self):
        return f"<ScheduledJob {self.name} ({self.cron_expression})>"


class JobExecutionLog(Base):
    """任务执行日志模型"""
    __tablename__ = "job_execution_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("scheduled_jobs.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default=JobStatus.PENDING.value)  # pending/running/success/failed/retrying
    output = Column(Text)  # 执行输出
    error = Column(Text)  # 错误信息
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    retry_number = Column(Integer, default=0)  # 第几次重试

    # 关系
    job = relationship("ScheduledJob", back_populates="execution_logs")

    __table_args__ = (
        Index("ix_job_log_job_status", "job_id", "status"),
        Index("ix_job_log_started", "started_at", "status"),
    )

    def __repr__(self):
        return f"<JobExecutionLog {self.job_id[:8]} {self.status}>"

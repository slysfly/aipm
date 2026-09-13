"""
异步任务模型 —— 支撑「后台执行 + 实时进度推送」能力。
所有耗时操作（AI 总结经验教训、生成 WBS、风险分析等）拆为异步任务，
由 asyncio 后台执行，进度经 WebSocket 事件总线实时推送到前端。
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, func
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.session import Base
import uuid
import enum


def generate_uuid():
    return str(uuid.uuid4())


class AsyncTaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class AsyncTask(Base):
    __tablename__ = "async_tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    task_type = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default=AsyncTaskStatus.PENDING.value, index=True)
    progress = Column(Integer, default=0)  # 0-100
    message = Column(String(500), default="")
    result = Column(JSON, default=None)
    error = Column(Text, default=None)
    params = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "task_type": self.task_type,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "params": self.params,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

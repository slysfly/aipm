from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Date, Numeric, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class Epic(Base):
    __tablename__ = "epics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(String(2000))
    color = Column(String(7), default="#1890ff")
    status = Column(String(20), default="backlog")
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    start_date = Column(Date)
    end_date = Column(Date)
    progress = Column(Numeric(5, 2), default=0)
    story_points_total = Column(Integer, default=0)
    story_points_completed = Column(Integer, default=0)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project")
    creator = relationship("User", foreign_keys=[created_by])
    epic_tasks = relationship("EpicTask", back_populates="epic", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_epic_project_status", "project_id", "status"),
    )

    def __repr__(self):
        return f"<Epic {self.name}>"


class EpicTask(Base):
    __tablename__ = "epic_tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    epic_id = Column(String(36), ForeignKey("epics.id"), nullable=False, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)

    epic = relationship("Epic", back_populates="epic_tasks")
    task = relationship("Task")

    __table_args__ = (
        Index("ix_epic_task_unique", "epic_id", "task_id", unique=True),
    )

    def __repr__(self):
        return f"<EpicTask epic={self.epic_id} task={self.task_id}>"

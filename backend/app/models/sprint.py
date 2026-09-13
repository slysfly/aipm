from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Date, Index, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class Sprint(Base):
    __tablename__ = "sprints"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    goal = Column(String(500))
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(20), default="planning")
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    velocity = Column(Integer, default=0)
    capacity = Column(Integer, default=0)
    acceptance_plan = Column(Text, nullable=True, default=None)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project")
    creator = relationship("User", foreign_keys=[created_by])
    sprint_tasks = relationship("SprintTask", back_populates="sprint", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_sprint_project_status", "project_id", "status"),
        Index("ix_sprint_dates", "start_date", "end_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "goal": self.goal,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status,
            "project_id": self.project_id,
            "velocity": self.velocity or 0,
            "capacity": self.capacity or 0,
            "acceptance_plan": self.acceptance_plan,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Sprint {self.name}>"


class SprintTask(Base):
    __tablename__ = "sprint_tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    sprint_id = Column(String(36), ForeignKey("sprints.id"), nullable=False, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    status = Column(String(20), default="active")
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    sprint = relationship("Sprint", back_populates="sprint_tasks")
    task = relationship("Task")

    __table_args__ = (
        Index("ix_sprint_task_unique", "sprint_id", "task_id", unique=True),
    )

    def __repr__(self):
        return f"<SprintTask sprint={self.sprint_id} task={self.task_id}>"

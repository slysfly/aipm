from sqlalchemy import Column, String, DateTime, ForeignKey, Date, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class Release(Base):
    __tablename__ = "releases"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    description = Column(String(2000))
    status = Column(String(20), default="planning")
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    release_date = Column(Date)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project")
    creator = relationship("User", foreign_keys=[created_by])
    release_tasks = relationship("ReleaseTask", back_populates="release", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_release_project_status", "project_id", "status"),
        Index("ix_release_date", "release_date"),
    )

    def __repr__(self):
        return f"<Release {self.name} v{self.version}>"


class ReleaseTask(Base):
    __tablename__ = "release_tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    release_id = Column(String(36), ForeignKey("releases.id"), nullable=False, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)

    release = relationship("Release", back_populates="release_tasks")
    task = relationship("Task")

    __table_args__ = (
        Index("ix_release_task_unique", "release_id", "task_id", unique=True),
    )

    def __repr__(self):
        return f"<ReleaseTask release={self.release_id} task={self.task_id}>"

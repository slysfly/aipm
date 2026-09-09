from sqlalchemy import text
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(String(2000))
    category = Column(String(50))
    fields = Column(JSON, default=dict)
    is_global = Column(Boolean, default=False)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    project = relationship("Project")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_template_global", "is_global"),
        Index("ix_template_project", "project_id"),
        Index("ix_template_category", "category"),
    )

    def __repr__(self):
        return f"<TaskTemplate {self.name}>"

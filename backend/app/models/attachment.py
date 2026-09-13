from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base
from app.models import generate_uuid


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)

    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    comment_id = Column(String(36), ForeignKey("comments.id"), nullable=True, index=True)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task", back_populates="attachments")
    project = relationship("Project")
    comment = relationship("Comment")
    user = relationship("User")

    __table_args__ = (
        Index("ix_attachment_task", "task_id", "created_at"),
        Index("ix_attachment_project", "project_id", "created_at"),
        Index("ix_attachment_uploader", "uploaded_by", "created_at"),
    )

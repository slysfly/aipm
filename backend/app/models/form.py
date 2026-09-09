from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 表单模型
支持表单模板构建和表单提交
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, JSON, Index, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.session import Base
from app.models import generate_uuid


class FormFieldType(str, enum.Enum):
    """表单字段类型枚举"""
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    EMAIL = "email"
    DATE = "date"
    SELECT = "select"
    MULTISELECT = "multiselect"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    FILE = "file"
    RATING = "rating"
    USER_SELECT = "user_select"
    PROJECT_SELECT = "project_select"


class SubmissionStatus(str, enum.Enum):
    """提交状态枚举"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSING = "processing"


class FormTemplate(Base):
    """表单模板模型"""
    __tablename__ = "form_templates"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    fields = Column(JSON, default=list)  # JSON数组，每个字段有type/name/label/required/options/placeholder/validation
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    is_published = Column(Boolean, default=False)
    embed_in_task = Column(Boolean, default=False)
    embed_in_project = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    creator = relationship("User")
    project = relationship("Project")
    submissions = relationship("FormSubmission", back_populates="form_template", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_form_template_project_active", "project_id", "is_active"),
        Index("ix_form_template_created_by", "created_by", "created_at"),
    )

    def __repr__(self):
        return f"<FormTemplate {self.name}>"


class FormSubmission(Base):
    """表单提交模型"""
    __tablename__ = "form_submissions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    form_id = Column(String(36), ForeignKey("form_templates.id"), nullable=False, index=True)
    data = Column(JSON, default=dict)  # 提交的表单数据
    submitted_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    submitted_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    status = Column(String(20), default=SubmissionStatus.PENDING.value)
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_comment = Column(Text)
    source_type = Column(String(50), nullable=True)  # task/project 等嵌入来源
    source_id = Column(String(36), nullable=True)  # 来源实体ID

    form_template = relationship("FormTemplate", back_populates="submissions")
    submitter = relationship("User", foreign_keys=[submitted_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    __table_args__ = (
        Index("ix_form_submission_form_id", "form_id", "submitted_at"),
        Index("ix_form_submission_submitter", "submitted_by", "submitted_at"),
        Index("ix_form_submission_status", "status", "submitted_at"),
        Index("ix_form_submission_source", "source_type", "source_id"),
    )

    def __repr__(self):
        return f"<FormSubmission {self.id[:8]} form={self.form_id[:8]}>"

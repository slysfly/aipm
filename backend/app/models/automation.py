from sqlalchemy import text
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    trigger_type = Column(String(50), nullable=False, index=True)
    trigger_conditions = Column(JSON, default=dict)
    actions = Column(JSON, default=list)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    is_global = Column(Boolean, default=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    project = relationship("Project")
    creator = relationship("User")

    __table_args__ = (
        Index("ix_automation_project", "project_id", "is_active"),
        Index("ix_automation_trigger", "trigger_type", "is_active"),
        Index("ix_automation_global", "is_global", "is_active"),
    )

    def __repr__(self):
        return f"<AutomationRule {self.name}>"

from sqlalchemy import text
"""
PMI中国AI项目管理社区 - AI Agent会话模型
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func
from app.db.session import Base
from app.models import generate_uuid


class AgentSession(Base):
    """Agent会话模型"""
    __tablename__ = "agent_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False, default="新对话")
    messages = Column(JSON, default=list)  # [{role, content, timestamp, action_type, executed_steps, result}]
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    def __repr__(self):
        return f"<AgentSession {self.title}>"

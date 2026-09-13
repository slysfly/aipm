"""OKR / 白板 / 文档 数据库模型（替代原内存存储）"""
import uuid
from sqlalchemy import Column, String, Integer, Text, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base


def _uuid():
    return str(uuid.uuid4())


class Objective(Base):
    """OKR 目标（含关键结果，关键结果以 JSON 存储）"""
    __tablename__ = "okrs"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    objective = Column(String(512), nullable=False)
    year = Column(String(16), default="2026")
    quarter = Column(String(16), default="Q3")
    owner = Column(String(128), default="")
    progress = Column(Integer, default=0)
    key_results = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "objective": self.objective,
            "year": self.year,
            "quarter": self.quarter,
            "owner": self.owner,
            "progress": self.progress,
            "keyResults": self.key_results or [],
            "createdAt": self.created_at.isoformat() if self.created_at else "",
        }


class Whiteboard(Base):
    """白板（便利贴以 JSON 存储）"""
    __tablename__ = "whiteboards"

    id = Column(String(36), primary_key=True, default=_uuid)
    title = Column(String(255), default="未命名白板")
    notes = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "notes": self.notes or [],
            "createdAt": self.created_at.isoformat() if self.created_at else "",
        }


class Document(Base):
    """文档"""
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    title = Column(String(512), nullable=False)
    content = Column(Text, default="")
    folder = Column(String(128), default="通用")
    author = Column(String(128), default="")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "folder": self.folder,
            "author": self.author,
            "updatedAt": self.updated_at.strftime("%Y-%m-%d") if self.updated_at else "",
        }

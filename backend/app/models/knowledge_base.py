from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 知识库模型
支持向量存储（pgvector）和文本匹配降级
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, JSON, Index, Enum, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.db.session import Base
from app.db.vector import embedding_column
from app.models import generate_uuid


class ShareType(str, enum.Enum):
    """知识库分享类型"""
    USER = "user"        # 指定用户
    GROUP = "group"      # 指定用户组
    SYSTEM = "system"    # 全系统可见（提供给整个系统使用）


class SharePermission(str, enum.Enum):
    """分享权限"""
    READ = "read"        # 可读、检索、问答
    WRITE = "write"      # 可读写（可上传/删除文档）


class KnowledgeBaseShare(Base):
    """知识库分享记录"""
    __tablename__ = "knowledge_base_shares"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    share_type = Column(String(20), default=ShareType.USER.value, nullable=False, index=True)
    target_id = Column(String(36), nullable=True, index=True)  # user_id 或 group_id；system 时为 NULL
    permission = Column(String(20), default=SharePermission.READ.value, nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    kb = relationship("KnowledgeBase", backref="shares")


class UserGroup(Base):
    """用户组（用于知识库分享给一组人）"""
    __tablename__ = "user_groups"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    members = relationship("UserGroupMember", back_populates="group", cascade="all, delete-orphan")


class UserGroupMember(Base):
    """用户组成员关系"""
    __tablename__ = "user_group_members"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    group_id = Column(String(36), ForeignKey("user_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    group = relationship("UserGroup", back_populates="members")


class DocumentStatus(str, enum.Enum):
    """文档状态枚举"""
    PENDING = "pending"      # 待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"        # 处理失败


class SourceType(str, enum.Enum):
    """文档来源类型"""
    FILE = "file"
    URL = "url"
    TEXT = "text"


class Visibility(str, enum.Enum):
    """知识库可见性"""
    PRIVATE = "private"    # 私密：仅创建者可用
    PUBLIC = "public"      # 公开：全系统可检索/问答（AI生成可选）


class KnowledgeBase(Base):
    """知识库模型"""
    __tablename__ = "knowledge_bases"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)

    # 可见性：private（仅自己） / public（全系统可检索/问答/AI生成）
    visibility = Column(String(20), default=Visibility.PRIVATE.value, index=True)

    # 关联项目（可选）
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)

    # Embedding模型配置
    embedding_model = Column(String(100), default="text-embedding-3-small")

    # 创建者
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    project = relationship("Project")
    creator = relationship("User")
    documents = relationship("KnowledgeDocument", back_populates="knowledge_base", cascade="all, delete-orphan")

    # 索引
    __table_args__ = (
        Index("ix_kb_project", "project_id"),
        Index("ix_kb_creator", "created_by"),
    )

    def __repr__(self):
        return f"<KnowledgeBase {self.name}>"

    def to_dict(self):
        # 关系可能未加载：已通过 selectinload 预加载时返回真实数量，否则安全返回 0
        try:
            docs = self.documents
            document_count = len(docs) if docs else 0
        except Exception:
            document_count = 0
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "visibility": self.visibility or Visibility.PRIVATE.value,
            "project_id": self.project_id,
            "embedding_model": self.embedding_model,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "document_count": document_count,
        }


class KnowledgeDocument(Base):
    """知识库文档模型"""
    __tablename__ = "knowledge_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    kb_id = Column(String(36), ForeignKey("knowledge_bases.id"), nullable=False, index=True)

    # 文档基本信息
    title = Column(String(500), nullable=False)
    content = Column(LargeBinary)  # 原始内容：文件存原始字节；文本存 utf-8 字节

    # 来源信息
    source_type = Column(String(20), default=SourceType.TEXT.value)
    source_url = Column(String(1000))  # URL来源
    file_path = Column(String(500))    # 文件路径
    file_name = Column(String(255))    # 原始文件名
    file_size = Column(Integer, default=0)
    mime_type = Column(String(100))

    # 处理状态
    status = Column(String(20), default=DocumentStatus.PENDING.value)
    chunk_count = Column(Integer, default=0)
    error_message = Column(Text)

    # 元数据
    meta_data = Column(JSON, default=dict)

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")

    # 索引
    __table_args__ = (
        Index("ix_kdoc_kb_status", "kb_id", "status"),
        Index("ix_kdoc_created", "created_at"),
    )

    def __repr__(self):
        return f"<KnowledgeDocument {self.title}>"

    def to_dict(self):
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "title": self.title,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "status": self.status,
            "chunk_count": self.chunk_count,
            "meta_data": self.meta_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KnowledgeChunk(Base):
    """知识库文档片段模型"""
    __tablename__ = "knowledge_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("knowledge_documents.id"), nullable=False, index=True)

    # 片段内容
    content = Column(Text, nullable=False)

    # 向量嵌入：PostgreSQL 用 pgvector 的 Vector 列（SQL 层最近邻检索）；
    # SQLite 用 JSON 列（Python 余弦，向后兼容）。维度见 app.db.vector.embedding_dim。
    embedding = Column(embedding_column())

    # 片段索引和位置
    chunk_index = Column(Integer, default=0)
    start_pos = Column(Integer, default=0)
    end_pos = Column(Integer, default=0)

    # 元数据
    meta_data = Column(JSON, default=dict)

    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    document = relationship("KnowledgeDocument", back_populates="chunks")

    # 索引
    __table_args__ = (
        Index("ix_kchunk_doc", "document_id"),
        Index("ix_kchunk_index", "document_id", "chunk_index"),
    )

    def __repr__(self):
        return f"<KnowledgeChunk doc={self.document_id[:8]} idx={self.chunk_index}>"

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.document_id,
            "content": (self.content.decode("utf-8", "ignore") if isinstance(self.content, (bytes, bytearray)) else self.content),
            "chunk_index": self.chunk_index,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "meta_data": self.meta_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

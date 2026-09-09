from sqlalchemy import text
"""
PMI中国AI项目管理社区 - Wiki知识库模型
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, Index, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class WikiSpace(Base):
    """Wiki知识空间"""
    __tablename__ = "wiki_spaces"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    icon = Column(String(50), default="book")
    color = Column(String(7), default="#1890ff")
    is_public = Column(Boolean, default=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    member_ids = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    owner = relationship("User")
    pages = relationship("WikiPage", back_populates="space", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<WikiSpace {self.name}>"


class WikiPage(Base):
    """Wiki页面"""
    __tablename__ = "wiki_pages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    space_id = Column(String(36), ForeignKey("wiki_spaces.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, default="")
    parent_id = Column(String(36), ForeignKey("wiki_pages.id"), nullable=True, index=True)
    order_index = Column(Integer, default=0)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    updated_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    version = Column(Integer, default=1)
    is_locked = Column(Boolean, default=False)
    lock_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    lock_expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    space = relationship("WikiSpace", back_populates="pages")
    parent = relationship("WikiPage", remote_side="WikiPage.id", backref="children")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    versions = relationship("WikiPageVersion", back_populates="page", cascade="all, delete-orphan")
    comments = relationship("WikiComment", back_populates="page", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_wiki_page_space_order", "space_id", "order_index"),
        Index("ix_wiki_page_parent", "space_id", "parent_id"),
    )

    def __repr__(self):
        return f"<WikiPage {self.title}>"


class WikiPageVersion(Base):
    """Wiki页面版本历史"""
    __tablename__ = "wiki_page_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    page_id = Column(String(36), ForeignKey("wiki_pages.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, default="")
    editor_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    edit_summary = Column(String(500))

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    page = relationship("WikiPage", back_populates="versions")
    editor = relationship("User")

    __table_args__ = (
        Index("ix_wiki_version_page_created", "page_id", "created_at"),
    )

    def __repr__(self):
        return f"<WikiPageVersion {self.page_id} v{self.id[:8]}>"


class WikiComment(Base):
    """Wiki页面评论"""
    __tablename__ = "wiki_comments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    page_id = Column(String(36), ForeignKey("wiki_pages.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    parent_id = Column(String(36), ForeignKey("wiki_comments.id"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    page = relationship("WikiPage", back_populates="comments")
    author = relationship("User")
    parent = relationship("WikiComment", remote_side="WikiComment.id", backref="replies")

    __table_args__ = (
        Index("ix_wiki_comment_page_created", "page_id", "created_at"),
    )

    def __repr__(self):
        return f"<WikiComment {self.id[:8]} by {self.author_id[:8]}>"

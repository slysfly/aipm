import enum
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean, JSON, Index, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base
from app.models import generate_uuid


class MessageType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"


class ChannelType(str, enum.Enum):
    DIRECT = "direct"
    GROUP = "group"
    PROJECT = "project"


class ChannelMemberRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    content = Column(Text, nullable=False)
    type = Column(String(20), default=MessageType.TEXT.value)
    sender_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    receiver_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    channel_id = Column(String(36), ForeignKey("channels.id"), nullable=True, index=True)
    thread_id = Column(String(36), ForeignKey("messages.id"), nullable=True, index=True)
    reply_to = Column(String(36), ForeignKey("messages.id"), nullable=True, index=True)
    mentions = Column(JSON, default=list)
    edited_at = Column(DateTime(timezone=True))
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
    channel = relationship("Channel", back_populates="messages")
    thread = relationship("Message", remote_side=[id], foreign_keys=[thread_id], backref="replies")
    reply = relationship("Message", remote_side=[id], foreign_keys=[reply_to], backref="reply_messages")
    reactions = relationship("MessageReaction", back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_message_channel_created", "channel_id", "created_at"),
        Index("ix_message_sender_created", "sender_id", "created_at"),
        Index("ix_message_receiver_created", "receiver_id", "created_at"),
    )


class Channel(Base):
    __tablename__ = "channels"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    type = Column(String(20), default=ChannelType.GROUP.value)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    member_ids = Column(JSON, default=list)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    messages = relationship("Message", back_populates="channel", cascade="all, delete-orphan")
    members = relationship("ChannelMember", back_populates="channel", cascade="all, delete-orphan")
    project = relationship("Project")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_channel_type_project", "type", "project_id"),
        Index("ix_channel_created_by", "created_by", "created_at"),
    )


class ChannelMember(Base):
    __tablename__ = "channel_members"

    channel_id = Column(String(36), ForeignKey("channels.id"), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    role = Column(String(20), default=ChannelMemberRole.MEMBER.value)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    last_read_at = Column(DateTime(timezone=True))

    channel = relationship("Channel", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        Index("ix_channel_member_user", "user_id", "joined_at"),
    )


class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    message_id = Column(String(36), ForeignKey("messages.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    emoji = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="reactions")
    user = relationship("User")

    __table_args__ = (
        Index("ix_reaction_message", "message_id", "created_at"),
        Index("ix_reaction_unique", "message_id", "user_id", "emoji", unique=True),
    )

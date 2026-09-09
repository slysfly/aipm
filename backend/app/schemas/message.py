from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.schemas import BaseSchema, PageResponse


class MessageBase(BaseSchema):
    content: str = Field(..., min_length=1)
    type: str = "text"
    mentions: List[str] = []


class MessageCreate(BaseSchema):
    content: str = Field(..., min_length=1)
    type: str = "text"
    receiver_id: Optional[str] = None
    thread_id: Optional[str] = None
    reply_to: Optional[str] = None
    mentions: List[str] = []


class MessageUpdate(BaseSchema):
    content: Optional[str] = Field(None, min_length=1)
    mentions: Optional[List[str]] = None


class MessageSenderInfo(BaseSchema):
    id: str
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class MessageReactionInfo(BaseSchema):
    id: str
    user_id: str
    emoji: str
    user: Optional[MessageSenderInfo] = None
    created_at: datetime


class MessageResponse(BaseSchema):
    id: str
    content: str
    type: str
    sender_id: str
    receiver_id: Optional[str] = None
    channel_id: Optional[str] = None
    thread_id: Optional[str] = None
    reply_to: Optional[str] = None
    mentions: List[str] = []
    edited_at: Optional[datetime] = None
    is_deleted: bool = False
    created_at: datetime
    sender: Optional[MessageSenderInfo] = None
    reactions: List[MessageReactionInfo] = []
    reply_count: int = 0


class MessageListResponse(PageResponse):
    items: List[MessageResponse]


class ChannelBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = "group"
    project_id: Optional[str] = None


class ChannelCreate(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = "group"
    project_id: Optional[str] = None
    member_ids: List[str] = []


class ChannelUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    member_ids: Optional[List[str]] = None


class ChannelMemberInfo(BaseSchema):
    channel_id: str
    user_id: str
    role: str = "member"
    joined_at: datetime
    last_read_at: Optional[datetime] = None
    user: Optional[MessageSenderInfo] = None


class ChannelResponse(BaseSchema):
    id: str
    name: str
    type: str
    project_id: Optional[str] = None
    member_ids: List[str] = []
    created_by: str
    created_at: datetime
    unread_count: int = 0
    last_message: Optional[MessageResponse] = None


class ChannelListResponse(PageResponse):
    items: List[ChannelResponse]


class ReactionCreate(BaseSchema):
    emoji: str = Field(..., min_length=1, max_length=50)


class ReadMarkerUpdate(BaseSchema):
    message_id: Optional[str] = None


class SuccessResponse(BaseSchema):
    success: bool = True
    message: Optional[str] = None

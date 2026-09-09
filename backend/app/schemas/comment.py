from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.schemas import BaseSchema, PageResponse


class CommentBase(BaseSchema):
    content: str = Field(..., min_length=1)
    mentions: List[str] = []


class CommentCreate(CommentBase):
    task_id: str
    project_id: Optional[str] = None
    parent_id: Optional[str] = None


class CommentUpdate(BaseSchema):
    content: Optional[str] = Field(None, min_length=1)
    mentions: Optional[List[str]] = None


class CommentUserInfo(BaseSchema):
    id: str
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class CommentResponse(BaseSchema):
    id: str
    content: str
    task_id: str
    project_id: Optional[str] = None
    user_id: str
    parent_id: Optional[str] = None
    mentions: List[str] = []
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime
    user: Optional[CommentUserInfo] = None
    replies: List["CommentResponse"] = []


class CommentListResponse(PageResponse):
    items: List[CommentResponse]


CommentResponse.model_rebuild()

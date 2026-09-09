from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.schemas import BaseSchema, PageResponse


class NotificationBase(BaseSchema):
    type: str
    title: str
    content: Optional[str] = None
    related_type: Optional[str] = None
    related_id: Optional[str] = None


class NotificationCreate(NotificationBase):
    user_id: str


class NotificationUpdate(BaseSchema):
    is_read: Optional[bool] = None


class NotificationResponse(BaseSchema):
    id: str
    user_id: str
    type: str
    title: str
    content: Optional[str] = None
    related_type: Optional[str] = None
    related_id: Optional[str] = None
    is_read: bool = False
    read_at: Optional[datetime] = None
    created_at: datetime


class NotificationListResponse(PageResponse):
    items: List[NotificationResponse]


class UnreadCountResponse(BaseSchema):
    count: int

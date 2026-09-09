from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.schemas import BaseSchema, PageResponse


class AttachmentBase(BaseSchema):
    filename: str
    original_name: str
    file_size: int
    mime_type: str


class AttachmentCreate(AttachmentBase):
    file_path: str
    task_id: Optional[str] = None
    project_id: Optional[str] = None
    comment_id: Optional[str] = None
    uploaded_by: str


class AttachmentResponse(BaseSchema):
    id: str
    filename: str
    original_name: str
    file_path: str
    file_size: int
    mime_type: str
    task_id: Optional[str] = None
    project_id: Optional[str] = None
    comment_id: Optional[str] = None
    uploaded_by: str
    created_at: datetime


class AttachmentListResponse(PageResponse):
    items: List[AttachmentResponse]

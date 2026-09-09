from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime, date

from app.schemas import BaseSchema


class ReleaseBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    version: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    status: str = "planning"
    project_id: str
    release_date: Optional[date] = None


class ReleaseCreate(ReleaseBase):
    pass


class ReleaseUpdate(BaseSchema):
    name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    release_date: Optional[date] = None


class ReleaseResponse(ReleaseBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class ReleaseTaskBase(BaseSchema):
    release_id: str
    task_id: str


class ReleaseTaskCreate(ReleaseTaskBase):
    pass


class ReleaseTaskResponse(ReleaseTaskBase):
    id: str


class ReleaseWithTasksResponse(ReleaseResponse):
    tasks: List[ReleaseTaskResponse] = []
    task_count: int = 0
    completed_task_count: int = 0


class ReleaseListResponse(BaseSchema):
    items: List[ReleaseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SuccessResponse(BaseModel):
    """通用成功响应"""
    success: bool = True
    message: str = "操作成功"
    data: Optional[Any] = None

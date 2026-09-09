from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime, date

from app.schemas import BaseSchema


class EpicBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    color: str = "#1890ff"
    status: str = "backlog"
    project_id: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    story_points_total: int = 0
    story_points_completed: int = 0


class EpicCreate(EpicBase):
    pass


class EpicUpdate(BaseSchema):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    story_points_total: Optional[int] = None
    story_points_completed: Optional[int] = None


class EpicResponse(EpicBase):
    id: str
    progress: float = 0
    created_by: str
    created_at: datetime
    updated_at: datetime


class EpicTaskBase(BaseSchema):
    epic_id: str
    task_id: str


class EpicTaskCreate(EpicTaskBase):
    pass


class EpicTaskResponse(EpicTaskBase):
    id: str


class EpicWithTasksResponse(EpicResponse):
    tasks: List[EpicTaskResponse] = []
    task_count: int = 0
    completed_task_count: int = 0


class EpicProgressUpdate(BaseSchema):
    story_points_completed: int


class EpicListResponse(BaseSchema):
    items: List[EpicResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SuccessResponse(BaseModel):
    """通用成功响应"""
    success: bool = True
    message: str = "操作成功"
    data: Optional[Any] = None

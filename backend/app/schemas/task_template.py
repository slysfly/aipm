from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.schemas import BaseSchema


class TaskTemplateBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    fields: Dict[str, Any] = {}
    is_global: bool = False
    project_id: Optional[str] = None


class TaskTemplateCreate(TaskTemplateBase):
    pass


class TaskTemplateUpdate(BaseSchema):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None
    is_global: Optional[bool] = None
    project_id: Optional[str] = None


class TaskTemplateResponse(TaskTemplateBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class TaskTemplateFromTaskCreate(BaseSchema):
    task_id: str
    name: str
    category: Optional[str] = None
    is_global: bool = False


class TaskFromTemplateCreate(BaseSchema):
    template_id: str
    project_id: str
    name: Optional[str] = None


class TaskTemplateListResponse(BaseSchema):
    items: List[TaskTemplateResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SuccessResponse(BaseModel):
    """通用成功响应"""
    success: bool = True
    message: str = "操作成功"
    data: Optional[Any] = None

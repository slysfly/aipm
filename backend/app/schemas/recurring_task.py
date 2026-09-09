from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.schemas import BaseSchema


class RecurringTaskBase(BaseSchema):
    """重复任务基础Schema"""
    base_task_id: Optional[str] = None
    project_id: str
    pattern: str = Field(..., pattern="^(daily|weekly|biweekly|monthly|quarterly|yearly|custom)$")
    interval_days: int = Field(default=1, ge=1)
    week_days: List[int] = Field(default_factory=list)
    month_day: int = Field(default=1, ge=1, le=31)
    end_condition: str = Field(default="never", pattern="^(never|after_count|on_date)$")
    end_after_count: int = Field(default=0, ge=0)
    end_date: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    is_active: bool = True


class RecurringTaskCreate(RecurringTaskBase):
    """创建重复任务"""
    pass


class RecurringTaskUpdate(BaseSchema):
    """更新重复任务"""
    pattern: Optional[str] = Field(None, pattern="^(daily|weekly|biweekly|monthly|quarterly|yearly|custom)$")
    interval_days: Optional[int] = Field(None, ge=1)
    week_days: Optional[List[int]] = None
    month_day: Optional[int] = Field(None, ge=1, le=31)
    end_condition: Optional[str] = Field(None, pattern="^(never|after_count|on_date)$")
    end_after_count: Optional[int] = Field(None, ge=0)
    end_date: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class RecurringTaskResponse(RecurringTaskBase):
    """重复任务响应"""
    id: str
    run_count: int = 0
    last_run_at: Optional[datetime] = None
    created_by: str
    created_at: datetime
    updated_at: datetime


class RecurringTaskListResponse(BaseSchema):
    """重复任务列表响应"""
    items: List[RecurringTaskResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RecurringTaskInstanceResponse(BaseSchema):
    """重复任务实例响应"""
    id: str
    recurring_task_id: str
    task_id: str
    generated_at: datetime
    sequence_number: int


class RecurringTaskInstanceListResponse(BaseSchema):
    """重复任务实例列表响应"""
    items: List[RecurringTaskInstanceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RecurringTaskToggleResponse(BaseSchema):
    """启用/停用响应"""
    id: str
    is_active: bool
    message: str


class RecurringTaskRunNowResponse(BaseSchema):
    """立即执行响应"""
    id: str
    task_id: str
    message: str


class RecurringTaskPreviewResponse(BaseSchema):
    """下次执行时间预览响应"""
    next_run_at: Optional[datetime] = None
    preview_dates: List[datetime] = Field(default_factory=list)

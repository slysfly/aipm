"""
PMI中国AI项目管理社区 - 定时任务Schema
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.schemas import BaseSchema


class ScheduledJobBase(BaseSchema):
    """定时任务基础Schema"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    job_type: str = Field(..., pattern="^(report|notification|cleanup|sync|ai_analysis)$")
    cron_expression: str = Field(..., min_length=1, max_length=100)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class ScheduledJobCreate(ScheduledJobBase):
    """创建定时任务"""
    pass


class ScheduledJobUpdate(BaseSchema):
    """更新定时任务"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    job_type: Optional[str] = Field(None, pattern="^(report|notification|cleanup|sync|ai_analysis)$")
    cron_expression: Optional[str] = Field(None, min_length=1, max_length=100)
    parameters: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ScheduledJobResponse(ScheduledJobBase):
    """定时任务响应"""
    id: str
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    run_count: int = 0
    fail_count: int = 0
    retry_count: int = 0
    created_by: str
    created_at: datetime
    updated_at: datetime


class ScheduledJobListResponse(BaseSchema):
    """定时任务列表响应"""
    items: List[ScheduledJobResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class JobExecutionLogResponse(BaseSchema):
    """任务执行日志响应"""
    id: str
    job_id: str
    status: str
    output: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_number: int = 0


class JobExecutionLogListResponse(BaseSchema):
    """任务执行日志列表响应"""
    items: List[JobExecutionLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ScheduledJobRunNowResponse(BaseSchema):
    """立即执行任务响应"""
    id: str
    log_id: str
    status: str
    message: str


class ScheduledJobToggleResponse(BaseSchema):
    """启用/停用任务响应"""
    id: str
    is_active: bool
    message: str


class CronPreset(BaseSchema):
    """Cron预设"""
    label: str
    value: str
    description: str


class CronPresetListResponse(BaseSchema):
    """Cron预设列表"""
    items: List[CronPreset]

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime, date

from app.schemas import BaseSchema


class SprintBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    goal: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: str = "planning"
    project_id: str
    velocity: int = 0
    capacity: int = 0
    acceptance_plan: Optional[str] = None


class SprintCreate(SprintBase):
    pass


class SprintUpdate(BaseSchema):
    name: Optional[str] = None
    goal: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    velocity: Optional[int] = None
    capacity: Optional[int] = None
    acceptance_plan: Optional[str] = None


class SprintResponse(SprintBase):
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class SprintTaskBase(BaseSchema):
    sprint_id: Optional[str] = None  # 从路径参数自动填充
    task_id: str
    status: str = "active"


class SprintTaskCreate(SprintTaskBase):
    pass


class SprintTaskResponse(SprintTaskBase):
    id: str
    added_at: datetime
    completed_at: Optional[datetime] = None


class SprintWithTasksResponse(SprintResponse):
    tasks: List[SprintTaskResponse] = []
    task_count: int = 0
    completed_task_count: int = 0


class SprintBurndownPoint(BaseSchema):
    date: date
    remaining: int
    ideal: int
    actual: int = 0  # 实际剩余（按每日完成统计）


class SprintBurnupPoint(BaseSchema):
    date: date
    total: int       # 累计总 scope（含新增）
    completed: int   # 累计完成
    ideal: int = 0   # 理想完成线


class SprintReportResponse(BaseSchema):
    sprint_id: str
    total_tasks: int
    completed_tasks: int
    burndown_data: List[SprintBurndownPoint]
    burnup_data: List[SprintBurnupPoint] = []
    velocity: int
    capacity: int
    completion_rate: float
    acceptance_plan: Optional[str] = None
    # 关联任务摘要（供前端直接展示，无需额外请求）
    tasks_summary: List[dict] = []


class SprintListResponse(BaseSchema):
    items: List[SprintResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SuccessResponse(BaseModel):
    """通用成功响应"""
    success: bool = True
    message: str = "操作成功"
    data: Optional[Any] = None

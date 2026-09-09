"""
PMI中国AI项目管理社区 - 预算/成本跟踪 Pydantic Schemas
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal


# ==================== 基础模型 ====================

class BudgetBase(BaseModel):
    """预算基础模型"""
    model_config = ConfigDict(from_attributes=True)

    total_budget: float = Field(default=0, ge=0)
    currency: str = Field(default="CNY", pattern="^(CNY|USD|EUR)$")
    labor_rate: float = Field(default=0, ge=0)
    overhead_rate: float = Field(default=0, ge=0, le=1)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class BudgetCreate(BudgetBase):
    """创建预算"""
    project_id: str


class BudgetUpdate(BaseModel):
    """更新预算"""
    model_config = ConfigDict(from_attributes=True)

    total_budget: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, pattern="^(CNY|USD|EUR)$")
    labor_rate: Optional[float] = Field(default=None, ge=0)
    overhead_rate: Optional[float] = Field(default=None, ge=0, le=1)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = Field(default=None, pattern="^(draft|active|exceeded|closed)$")


class BudgetResponse(BudgetBase):
    """预算响应"""
    id: str
    project_id: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    # 计算字段
    total_spent: float = 0
    total_remaining: float = 0
    execution_rate: float = 0
    is_over_budget: bool = False


# ==================== 预算分类 ====================

class BudgetCategoryBase(BaseModel):
    """预算分类基础模型"""
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=100)
    allocated_amount: float = Field(default=0, ge=0)
    description: Optional[str] = None


class BudgetCategoryCreate(BudgetCategoryBase):
    """创建预算分类"""
    budget_id: str


class BudgetCategoryUpdate(BaseModel):
    """更新预算分类"""
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    allocated_amount: Optional[float] = Field(default=None, ge=0)
    description: Optional[str] = None


class BudgetCategoryResponse(BudgetCategoryBase):
    """预算分类响应"""
    id: str
    budget_id: str
    spent_amount: float = 0
    created_at: datetime
    updated_at: datetime

    # 计算字段
    remaining: float = 0
    execution_rate: float = 0
    is_over_budget: bool = False


# ==================== 成本记录 ====================

class CostRecordBase(BaseModel):
    """成本记录基础模型"""
    model_config = ConfigDict(from_attributes=True)

    cost_type: str = Field(default="other", pattern="^(labor|material|overhead|travel|other)$")
    amount: float = Field(default=0, ge=0)
    description: Optional[str] = None
    receipt_url: Optional[str] = None

    # 人工成本专用
    work_hours: Optional[float] = Field(default=None, ge=0)


class CostRecordCreate(CostRecordBase):
    """创建成本记录"""
    project_id: str
    budget_id: str
    category_id: Optional[str] = None
    task_id: Optional[str] = None


class CostRecordUpdate(BaseModel):
    """更新成本记录"""
    model_config = ConfigDict(from_attributes=True)

    cost_type: Optional[str] = Field(default=None, pattern="^(labor|material|overhead|travel|other)$")
    amount: Optional[float] = Field(default=None, ge=0)
    description: Optional[str] = None
    category_id: Optional[str] = None
    task_id: Optional[str] = None
    receipt_url: Optional[str] = None
    work_hours: Optional[float] = Field(default=None, ge=0)


class CostRecordResponse(CostRecordBase):
    """成本记录响应"""
    id: str
    project_id: str
    budget_id: str
    category_id: Optional[str] = None
    task_id: Optional[str] = None
    recorded_by: str
    recorded_at: datetime
    created_at: datetime
    labor_rate_at_record: float = 0

    # 关联信息
    task_name: Optional[str] = None
    recorder_name: Optional[str] = None
    category_name: Optional[str] = None


class CostRecordListResponse(BaseModel):
    """成本记录列表响应"""
    model_config = ConfigDict(from_attributes=True)

    items: List[CostRecordResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== 预算报告 ====================

class BudgetReportResponse(BaseModel):
    """预算执行报告响应"""
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    budget_id: Optional[str] = None
    total_budget: float = 0
    total_spent: float = 0
    total_remaining: float = 0
    execution_rate: float = 0
    currency: str = "CNY"
    is_over_budget: bool = False

    # 按类型统计
    cost_by_type: dict = {}

    # 按分类统计
    cost_by_category: List[dict] = []

    # 预警信息
    alerts: List[str] = []

    # 人工成本
    total_labor_hours: float = 0
    total_labor_cost: float = 0


class BudgetTrendItem(BaseModel):
    """预算趋势单项"""
    model_config = ConfigDict(from_attributes=True)

    month: str
    year: int
    month_num: int
    labor_cost: float = 0
    material_cost: float = 0
    overhead_cost: float = 0
    travel_cost: float = 0
    other_cost: float = 0
    total_cost: float = 0
    cumulative_cost: float = 0


class BudgetTrendResponse(BaseModel):
    """预算趋势响应"""
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    currency: str = "CNY"
    data: List[BudgetTrendItem] = []


# ==================== 预算概览 ====================

class BudgetOverviewResponse(BaseModel):
    """预算概览响应"""
    model_config = ConfigDict(from_attributes=True)

    project_id: str
    has_budget: bool = False
    budget: Optional[BudgetResponse] = None
    categories: List[BudgetCategoryResponse] = []
    recent_costs: List[CostRecordResponse] = []
    total_cost_records: int = 0

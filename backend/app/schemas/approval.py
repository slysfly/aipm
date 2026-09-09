"""
PMI中国AI项目管理社区 - 审批流程Schemas
"""

from pydantic import BaseModel, Field, ConfigDict, computed_field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== 流程步骤定义 ====================

class FlowStepSchema(BaseModel):
    """流程步骤定义"""
    model_config = ConfigDict(from_attributes=True)

    step_order: Optional[int] = None
    name: str = Field(default="", max_length=255)
    approver_role: Optional[str] = None
    approver_id: Optional[str] = None
    condition: Optional[str] = None  # 条件表达式，如 "amount > 10000"


# ==================== 审批流程定义 ====================

class ApprovalFlowBase(BaseModel):
    """审批流程基础模型"""
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    entity_type: str = Field(..., pattern="^(task|budget|leave|expense|change_request)$")
    steps: List[FlowStepSchema] = []
    is_active: bool = True


class ApprovalFlowCreate(ApprovalFlowBase):
    """创建审批流程"""
    pass


class ApprovalFlowUpdate(BaseModel):
    """更新审批流程"""
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = None
    description: Optional[str] = None
    entity_type: Optional[str] = None
    steps: Optional[List[FlowStepSchema]] = None
    is_active: Optional[bool] = None


class ApprovalFlowResponse(ApprovalFlowBase):
    """审批流程响应"""
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class ApprovalFlowListResponse(BaseModel):
    """审批流程列表响应"""
    model_config = ConfigDict(from_attributes=True)

    items: List[ApprovalFlowResponse]
    total: int


# ==================== 审批实例 ====================

class ApprovalInstanceBase(BaseModel):
    """审批实例基础模型"""
    model_config = ConfigDict(from_attributes=True)

    flow_id: str
    entity_type: str
    entity_id: str
    requester_id: str


class ApprovalInstanceCreate(BaseModel):
    """创建审批实例请求"""
    model_config = ConfigDict(from_attributes=True)

    flow_id: str
    entity_type: str
    entity_id: str


class ApprovalInstanceResponse(BaseModel):
    """审批实例响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    flow_id: str
    entity_type: str
    entity_id: str
    requester_id: str
    status: str
    current_step: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    flow: Optional[ApprovalFlowResponse] = None
    steps: List["ApprovalStepResponse"] = []


class ApprovalInstanceListResponse(BaseModel):
    """审批实例列表响应"""
    model_config = ConfigDict(from_attributes=True)

    items: List[ApprovalInstanceResponse]
    total: int


# ==================== 审批步骤 ====================

class ApprovalStepBase(BaseModel):
    """审批步骤基础模型"""
    model_config = ConfigDict(from_attributes=True)

    instance_id: str
    step_order: int
    approver_id: str


class ApprovalStepResponse(BaseModel):
    """审批步骤响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    instance_id: str
    step_order: int
    approver_id: str
    original_approver_id: Optional[str] = None
    status: str
    comment: Optional[str] = None
    acted_at: Optional[datetime] = None
    created_at: datetime
    approver: Optional[Dict[str, Any]] = None

    @field_validator("approver", mode="before")
    @classmethod
    def coerce_approver(cls, v, info):
        if v is None or isinstance(v, dict):
            return v
        # v is a User ORM object from from_attributes; extract minimal info
        return {"id": getattr(v, "id", info.data.get("approver_id", ""))}


class ApprovalActionRequest(BaseModel):
    """审批操作请求"""
    model_config = ConfigDict(from_attributes=True)

    comment: Optional[str] = None


class ApprovalTransferRequest(BaseModel):
    """转交请求"""
    model_config = ConfigDict(from_attributes=True)

    transfer_to: str
    comment: Optional[str] = None


# ==================== 审批委托 ====================

class ApprovalDelegateBase(BaseModel):
    """审批委托基础模型"""
    model_config = ConfigDict(from_attributes=True)

    delegatee_id: str
    start_date: datetime
    end_date: datetime
    is_active: bool = True


class ApprovalDelegateCreate(ApprovalDelegateBase):
    """创建审批委托"""
    pass


class ApprovalDelegateUpdate(BaseModel):
    """更新审批委托"""
    model_config = ConfigDict(from_attributes=True)

    delegatee_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None


class ApprovalDelegateResponse(ApprovalDelegateBase):
    """审批委托响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    delegator_id: str
    created_at: datetime
    delegator: Optional[Dict[str, Any]] = None
    delegatee: Optional[Dict[str, Any]] = None


class ApprovalDelegateListResponse(BaseModel):
    """审批委托列表响应"""
    model_config = ConfigDict(from_attributes=True)

    items: List[ApprovalDelegateResponse]
    total: int


# ==================== 审批仪表盘 ====================

class ApprovalDashboardResponse(BaseModel):
    """审批仪表盘响应"""
    model_config = ConfigDict(from_attributes=True)

    pending_count: int
    approved_count: int
    rejected_count: int
    avg_approval_duration_minutes: Optional[float] = None
    delegated_count: int
    total_requests: int


# Forward reference update
ApprovalInstanceResponse.model_rebuild()

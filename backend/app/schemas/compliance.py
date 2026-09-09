"""
PMI中国AI项目管理社区 - 合规模块 Pydantic Schemas
用于SOC2/ISO27001合规API的请求和响应数据验证
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date

from app.schemas import BaseSchema


# ==================== 合规策略 ====================

class CompliancePolicyBase(BaseSchema):
    """合规策略基础模型"""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = "security"
    status: str = "draft"
    version: str = "1.0"
    effective_date: Optional[date] = None
    review_cycle_days: int = Field(default=365, ge=1)
    owner_id: Optional[str] = None
    document_url: Optional[str] = None


class CompliancePolicyCreate(CompliancePolicyBase):
    """创建合规策略"""
    pass


class CompliancePolicyUpdate(BaseSchema):
    """更新合规策略"""
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    version: Optional[str] = None
    effective_date: Optional[date] = None
    review_cycle_days: Optional[int] = None
    owner_id: Optional[str] = None
    document_url: Optional[str] = None


class CompliancePolicyResponse(CompliancePolicyBase):
    """合规策略响应"""
    id: str
    created_at: datetime
    updated_at: datetime
    owner: Optional[Dict[str, Any]] = None
    control_count: int = 0


class CompliancePolicyListResponse(BaseSchema):
    """合规策略列表响应"""
    items: List[CompliancePolicyResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== 控制措施 ====================

class ComplianceControlBase(BaseSchema):
    """控制措施基础模型"""
    control_code: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    implementation_status: str = "not_implemented"
    evidence_required: bool = True
    last_tested_at: Optional[datetime] = None
    next_test_due: Optional[datetime] = None
    risk_level: str = "medium"


class ComplianceControlCreate(ComplianceControlBase):
    """创建控制措施"""
    policy_id: str


class ComplianceControlUpdate(BaseSchema):
    """更新控制措施"""
    control_code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    implementation_status: Optional[str] = None
    evidence_required: Optional[bool] = None
    last_tested_at: Optional[datetime] = None
    next_test_due: Optional[datetime] = None
    risk_level: Optional[str] = None


class ComplianceControlResponse(ComplianceControlBase):
    """控制措施响应"""
    id: str
    policy_id: str
    created_at: datetime
    policy: Optional[Dict[str, Any]] = None
    audit_count: int = 0
    evidence_count: int = 0


class ComplianceControlListResponse(BaseSchema):
    """控制措施列表响应"""
    items: List[ComplianceControlResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ControlTestRequest(BaseSchema):
    """控制措施测试请求"""
    findings: Optional[str] = None
    status: str = "pass"
    evidence_links: List[str] = []
    next_test_due: Optional[datetime] = None


class ControlTestResponse(BaseSchema):
    """控制措施测试响应"""
    control_id: str
    audit_id: str
    status: str
    tested_at: datetime
    message: str = "测试完成"


# ==================== 审计记录 ====================

class ComplianceAuditBase(BaseSchema):
    """审计记录基础模型"""
    audit_type: str = "scheduled"
    findings: Optional[str] = None
    status: str = "pass"
    evidence_links: List[str] = []
    conducted_at: Optional[datetime] = None


class ComplianceAuditCreate(ComplianceAuditBase):
    """创建审计记录"""
    control_id: str
    auditor_id: Optional[str] = None


class ComplianceAuditResponse(ComplianceAuditBase):
    """审计记录响应"""
    id: str
    control_id: str
    auditor_id: Optional[str] = None
    created_at: datetime
    auditor: Optional[Dict[str, Any]] = None
    control: Optional[Dict[str, Any]] = None


class ComplianceAuditListResponse(BaseSchema):
    """审计记录列表响应"""
    items: List[ComplianceAuditResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== 证据 ====================

class ComplianceEvidenceBase(BaseSchema):
    """证据基础模型"""
    file_url: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None


class ComplianceEvidenceCreate(ComplianceEvidenceBase):
    """创建证据"""
    control_id: str


class ComplianceEvidenceResponse(ComplianceEvidenceBase):
    """证据响应"""
    id: str
    control_id: str
    uploaded_by: str
    created_at: datetime
    uploader: Optional[Dict[str, Any]] = None


class ComplianceEvidenceListResponse(BaseSchema):
    """证据列表响应"""
    items: List[ComplianceEvidenceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ==================== 仪表盘和报告 ====================

class ComplianceDashboardResponse(BaseSchema):
    """合规仪表盘响应"""
    policy_total: int
    control_total: int
    control_pass_rate: float
    audits_pending: int
    risk_distribution: Dict[str, int]
    implementation_status_distribution: Dict[str, int]
    audit_status_distribution: Dict[str, int]
    upcoming_audits: List[Dict[str, Any]]
    recent_audits: List[Dict[str, Any]]


class ComplianceSummaryReportResponse(BaseSchema):
    """合规摘要报告响应"""
    generated_at: datetime
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    summary: Dict[str, Any]
    policy_summary: List[Dict[str, Any]]
    control_summary: List[Dict[str, Any]]
    audit_summary: List[Dict[str, Any]]
    recommendations: List[str]

"""
PMI中国AI项目管理社区 - SOC2/ISO27001 合规模块 API 路由
提供合规策略、控制措施、审计记录和证据的RESTful接口

[PMBOK KA: 质量管理 | PG: 监控 (Quality/Monitoring) — 合规检查、质量标准、审计跟踪]
对应PMI第6版标准：质量管理、合规审计、质量标准

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: Trustworthy AI — 可信AI合规治理]
PMBOK 7th Principle: Quality/Stewardship | Domain: Project Work — 质量融入、尽责管理
PMBOK 8th: ESG/Trustworthy Governance
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date

from app.db.session import get_db
from app.models import User
from app.schemas.compliance import (
    CompliancePolicyCreate, CompliancePolicyUpdate, CompliancePolicyResponse,
    CompliancePolicyListResponse,
    ComplianceControlCreate, ComplianceControlUpdate, ComplianceControlResponse,
    ComplianceControlListResponse, ControlTestRequest, ControlTestResponse,
    ComplianceAuditCreate, ComplianceAuditResponse, ComplianceAuditListResponse,
    ComplianceEvidenceCreate, ComplianceEvidenceResponse,
    ComplianceEvidenceListResponse,
    ComplianceDashboardResponse, ComplianceSummaryReportResponse,
)
from app.core.security import get_current_user
from app.core.security_compliance import audit_log, require_compliance_role

from . import service

router = APIRouter()


# ==================== 合规策略 ====================

@router.post("/policies", response_model=CompliancePolicyResponse, status_code=201)
@audit_log(action="create", entity_type="compliance_policy")
async def create_policy(
    policy_in: CompliancePolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance_role()),
):
    return await service.create_policy(db, policy_in, current_user)


@router.get("/policies", response_model=CompliancePolicyListResponse)
async def list_policies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await service.list_policies(db, page, page_size, category, status, search)


@router.get("/policies/{policy_id}", response_model=CompliancePolicyResponse)
async def get_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await service.get_policy(db, policy_id)


@router.put("/policies/{policy_id}", response_model=CompliancePolicyResponse)
@audit_log(action="update", entity_type="compliance_policy")
async def update_policy(
    policy_id: str,
    policy_in: CompliancePolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance_role()),
):
    return await service.update_policy(db, policy_id, policy_in)


@router.delete("/policies/{policy_id}")
@audit_log(action="delete", entity_type="compliance_policy")
async def delete_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance_role()),
):
    return await service.delete_policy(db, policy_id)


# ==================== 控制措施 ====================

@router.post("/controls", response_model=ComplianceControlResponse, status_code=201)
@audit_log(action="create", entity_type="compliance_control")
async def create_control(
    control_in: ComplianceControlCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance_role()),
):
    return await service.create_control(db, control_in, current_user)


@router.get("/controls", response_model=ComplianceControlListResponse)
async def list_controls(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    policy_id: Optional[str] = None,
    implementation_status: Optional[str] = None,
    risk_level: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await service.list_controls(db, page, page_size, policy_id, implementation_status, risk_level, search)


@router.get("/controls/{control_id}", response_model=ComplianceControlResponse)
async def get_control(
    control_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await service.get_control(db, control_id)


@router.put("/controls/{control_id}", response_model=ComplianceControlResponse)
@audit_log(action="update", entity_type="compliance_control")
async def update_control(
    control_id: str,
    control_in: ComplianceControlUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance_role()),
):
    return await service.update_control(db, control_id, control_in)


@router.delete("/controls/{control_id}")
@audit_log(action="delete", entity_type="compliance_control")
async def delete_control(
    control_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance_role()),
):
    return await service.delete_control(db, control_id)


@router.post("/controls/{control_id}/test", response_model=ControlTestResponse)
@audit_log(action="test", entity_type="compliance_control")
async def test_control(
    control_id: str,
    test_in: ControlTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance_role()),
):
    return await service.test_control(db, control_id, test_in, current_user)


# ==================== 审计记录 ====================

@router.post("/audits", response_model=ComplianceAuditResponse, status_code=201)
@audit_log(action="create", entity_type="compliance_audit")
async def create_audit(
    audit_in: ComplianceAuditCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance_role()),
):
    return await service.create_audit(db, audit_in, current_user)


@router.get("/audits", response_model=ComplianceAuditListResponse)
async def list_audits(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    control_id: Optional[str] = None,
    audit_type: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await service.list_audits(db, page, page_size, control_id, audit_type, status)


@router.get("/audits/{audit_id}", response_model=ComplianceAuditResponse)
async def get_audit(
    audit_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await service.get_audit(db, audit_id)


# ==================== 证据 ====================

@router.post("/evidences", response_model=ComplianceEvidenceResponse, status_code=201)
async def create_evidence(
    evidence_in: ComplianceEvidenceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance_role()),
):
    return await service.create_evidence(db, evidence_in, current_user)


@router.get("/evidences", response_model=ComplianceEvidenceListResponse)
async def list_evidences(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    control_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await service.list_evidences(db, page, page_size, control_id)


# ==================== 仪表盘 ====================

@router.get("/dashboard", response_model=ComplianceDashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await service.get_dashboard(db)


# ==================== 报告 ====================

@router.get("/reports/summary", response_model=ComplianceSummaryReportResponse)
async def get_summary_report(
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance_role()),
):
    return await service.get_summary_report(db, period_start, period_end)

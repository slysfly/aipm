"""
PMI中国AI项目管理社区 - 合规模块 业务逻辑层
"""

from datetime import datetime, timedelta, date

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.compliance import (
    CompliancePolicy, ComplianceControl, ComplianceAudit, ComplianceEvidence,
    ComplianceStatus, ControlImplementationStatus,
    RiskLevel, AuditType, AuditStatus,
)
from app.schemas.compliance import (
    CompliancePolicyCreate, CompliancePolicyUpdate,
    CompliancePolicyResponse, CompliancePolicyListResponse,
    ComplianceControlCreate, ComplianceControlUpdate,
    ComplianceControlResponse, ComplianceControlListResponse,
    ControlTestRequest, ControlTestResponse,
    ComplianceAuditCreate, ComplianceAuditResponse, ComplianceAuditListResponse,
    ComplianceEvidenceCreate, ComplianceEvidenceResponse,
    ComplianceEvidenceListResponse,
    ComplianceDashboardResponse, ComplianceSummaryReportResponse,
)
from app.core.exceptions import NotFoundException, ValidationException


# ==================== 合规策略 ====================


async def create_policy(
    db: AsyncSession,
    policy_in: CompliancePolicyCreate,
    current_user: User,
) -> CompliancePolicy:
    policy = CompliancePolicy(
        title=policy_in.title,
        description=policy_in.description,
        category=policy_in.category,
        status=policy_in.status,
        version=policy_in.version,
        effective_date=policy_in.effective_date,
        review_cycle_days=policy_in.review_cycle_days,
        owner_id=policy_in.owner_id or current_user.id,
        document_url=policy_in.document_url,
    )

    db.add(policy)
    await db.commit()
    await db.refresh(policy)

    return policy


async def list_policies(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> CompliancePolicyListResponse:
    query = select(CompliancePolicy)
    count_query = select(func.count(CompliancePolicy.id))

    if category:
        query = query.where(CompliancePolicy.category == category)
        count_query = count_query.where(CompliancePolicy.category == category)

    if status:
        query = query.where(CompliancePolicy.status == status)
        count_query = count_query.where(CompliancePolicy.status == status)

    if search:
        search_filter = or_(
            CompliancePolicy.title.ilike(f"%{search}%"),
            CompliancePolicy.description.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(CompliancePolicy.created_at.desc())

    result = await db.execute(query)
    policies = result.scalars().all()

    # 获取每个策略的控制措施数量
    policy_ids = [p.id for p in policies]
    control_counts = {}
    if policy_ids:
        count_stmt = (
            select(ComplianceControl.policy_id, func.count(ComplianceControl.id))
            .where(ComplianceControl.policy_id.in_(policy_ids))
            .group_by(ComplianceControl.policy_id)
        )
        count_result = await db.execute(count_stmt)
        for pid, cnt in count_result.all():
            control_counts[pid] = cnt

    items = []
    for p in policies:
        data = CompliancePolicyResponse.model_validate(p)
        data.control_count = control_counts.get(p.id, 0)
        items.append(data)

    total_pages = (total + page_size - 1) // page_size

    return CompliancePolicyListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


async def get_policy(
    db: AsyncSession,
    policy_id: str,
) -> CompliancePolicy:
    result = await db.execute(select(CompliancePolicy).where(CompliancePolicy.id == policy_id))
    policy = result.scalar_one_or_none()

    if not policy:
        raise NotFoundException(message="合规策略不存在")

    return policy


async def update_policy(
    db: AsyncSession,
    policy_id: str,
    policy_in: CompliancePolicyUpdate,
) -> CompliancePolicy:
    result = await db.execute(select(CompliancePolicy).where(CompliancePolicy.id == policy_id))
    policy = result.scalar_one_or_none()

    if not policy:
        raise NotFoundException(message="合规策略不存在")

    update_data = policy_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(policy, field, value)

    policy.updated_at = datetime.now()

    await db.commit()
    await db.refresh(policy)

    return policy


async def delete_policy(
    db: AsyncSession,
    policy_id: str,
) -> dict:
    result = await db.execute(select(CompliancePolicy).where(CompliancePolicy.id == policy_id))
    policy = result.scalar_one_or_none()

    if not policy:
        raise NotFoundException(message="合规策略不存在")

    await db.delete(policy)
    await db.commit()

    return {"success": True, "message": "合规策略删除成功"}


# ==================== 控制措施 ====================


async def create_control(
    db: AsyncSession,
    control_in: ComplianceControlCreate,
    current_user: User,
) -> ComplianceControl:
    policy_result = await db.execute(
        select(CompliancePolicy).where(CompliancePolicy.id == control_in.policy_id)
    )
    policy = policy_result.scalar_one_or_none()
    if not policy:
        raise NotFoundException(message="关联的合规策略不存在")

    control = ComplianceControl(
        policy_id=control_in.policy_id,
        control_code=control_in.control_code,
        title=control_in.title,
        description=control_in.description,
        implementation_status=control_in.implementation_status,
        evidence_required=control_in.evidence_required,
        last_tested_at=control_in.last_tested_at,
        next_test_due=control_in.next_test_due,
        risk_level=control_in.risk_level,
    )

    db.add(control)
    await db.commit()
    await db.refresh(control)

    return control


async def list_controls(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    policy_id: str | None = None,
    implementation_status: str | None = None,
    risk_level: str | None = None,
    search: str | None = None,
) -> ComplianceControlListResponse:
    query = select(ComplianceControl)
    count_query = select(func.count(ComplianceControl.id))

    if policy_id:
        query = query.where(ComplianceControl.policy_id == policy_id)
        count_query = count_query.where(ComplianceControl.policy_id == policy_id)

    if implementation_status:
        query = query.where(ComplianceControl.implementation_status == implementation_status)
        count_query = count_query.where(ComplianceControl.implementation_status == implementation_status)

    if risk_level:
        query = query.where(ComplianceControl.risk_level == risk_level)
        count_query = count_query.where(ComplianceControl.risk_level == risk_level)

    if search:
        search_filter = or_(
            ComplianceControl.title.ilike(f"%{search}%"),
            ComplianceControl.control_code.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(ComplianceControl.created_at.desc())

    result = await db.execute(query)
    controls = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return ComplianceControlListResponse(
        items=[ComplianceControlResponse.model_validate(c) for c in controls],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


async def get_control(
    db: AsyncSession,
    control_id: str,
) -> ComplianceControl:
    result = await db.execute(select(ComplianceControl).where(ComplianceControl.id == control_id))
    control = result.scalar_one_or_none()

    if not control:
        raise NotFoundException(message="控制措施不存在")

    return control


async def update_control(
    db: AsyncSession,
    control_id: str,
    control_in: ComplianceControlUpdate,
) -> ComplianceControl:
    result = await db.execute(select(ComplianceControl).where(ComplianceControl.id == control_id))
    control = result.scalar_one_or_none()

    if not control:
        raise NotFoundException(message="控制措施不存在")

    update_data = control_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(control, field, value)

    await db.commit()
    await db.refresh(control)

    return control


async def delete_control(
    db: AsyncSession,
    control_id: str,
) -> dict:
    result = await db.execute(select(ComplianceControl).where(ComplianceControl.id == control_id))
    control = result.scalar_one_or_none()

    if not control:
        raise NotFoundException(message="控制措施不存在")

    await db.delete(control)
    await db.commit()

    return {"success": True, "message": "控制措施删除成功"}


async def test_control(
    db: AsyncSession,
    control_id: str,
    test_in: ControlTestRequest,
    current_user: User,
) -> ControlTestResponse:
    result = await db.execute(select(ComplianceControl).where(ComplianceControl.id == control_id))
    control = result.scalar_one_or_none()

    if not control:
        raise NotFoundException(message="控制措施不存在")

    now = datetime.now()
    next_due = test_in.next_test_due or (now + timedelta(days=90))

    # 更新控制措施状态
    control.last_tested_at = now
    control.next_test_due = next_due
    if test_in.status == "pass":
        control.implementation_status = ControlImplementationStatus.IMPLEMENTED.value
    elif test_in.status == "fail":
        control.implementation_status = ControlImplementationStatus.NOT_IMPLEMENTED.value
    else:
        control.implementation_status = ControlImplementationStatus.PARTIALLY_IMPLEMENTED.value

    # 创建审计记录
    audit = ComplianceAudit(
        control_id=control_id,
        auditor_id=current_user.id,
        audit_type=AuditType.AD_HOC.value,
        findings=test_in.findings,
        status=test_in.status,
        evidence_links=test_in.evidence_links,
        conducted_at=now,
    )
    db.add(audit)

    await db.commit()
    await db.refresh(audit)

    return ControlTestResponse(
        control_id=control_id,
        audit_id=audit.id,
        status=test_in.status,
        tested_at=now,
        message="测试完成",
    )


# ==================== 审计记录 ====================


async def create_audit(
    db: AsyncSession,
    audit_in: ComplianceAuditCreate,
    current_user: User,
) -> ComplianceAudit:
    control_result = await db.execute(
        select(ComplianceControl).where(ComplianceControl.id == audit_in.control_id)
    )
    control = control_result.scalar_one_or_none()
    if not control:
        raise NotFoundException(message="关联的控制措施不存在")

    audit = ComplianceAudit(
        control_id=audit_in.control_id,
        auditor_id=audit_in.auditor_id or current_user.id,
        audit_type=audit_in.audit_type,
        findings=audit_in.findings,
        status=audit_in.status,
        evidence_links=audit_in.evidence_links,
        conducted_at=audit_in.conducted_at or datetime.now(),
    )

    db.add(audit)
    await db.commit()
    await db.refresh(audit)

    return audit


async def list_audits(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    control_id: str | None = None,
    audit_type: str | None = None,
    status: str | None = None,
) -> ComplianceAuditListResponse:
    query = select(ComplianceAudit)
    count_query = select(func.count(ComplianceAudit.id))

    if control_id:
        query = query.where(ComplianceAudit.control_id == control_id)
        count_query = count_query.where(ComplianceAudit.control_id == control_id)

    if audit_type:
        query = query.where(ComplianceAudit.audit_type == audit_type)
        count_query = count_query.where(ComplianceAudit.audit_type == audit_type)

    if status:
        query = query.where(ComplianceAudit.status == status)
        count_query = count_query.where(ComplianceAudit.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(ComplianceAudit.created_at.desc())

    result = await db.execute(query)
    audits = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return ComplianceAuditListResponse(
        items=[ComplianceAuditResponse.model_validate(a) for a in audits],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


async def get_audit(
    db: AsyncSession,
    audit_id: str,
) -> ComplianceAudit:
    result = await db.execute(select(ComplianceAudit).where(ComplianceAudit.id == audit_id))
    audit = result.scalar_one_or_none()

    if not audit:
        raise NotFoundException(message="审计记录不存在")

    return audit


# ==================== 证据 ====================


async def create_evidence(
    db: AsyncSession,
    evidence_in: ComplianceEvidenceCreate,
    current_user: User,
) -> ComplianceEvidence:
    control_result = await db.execute(
        select(ComplianceControl).where(ComplianceControl.id == evidence_in.control_id)
    )
    control = control_result.scalar_one_or_none()
    if not control:
        raise NotFoundException(message="关联的控制措施不存在")

    evidence = ComplianceEvidence(
        control_id=evidence_in.control_id,
        file_url=evidence_in.file_url,
        description=evidence_in.description,
        uploaded_by=current_user.id,
    )

    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)

    return evidence


async def list_evidences(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    control_id: str | None = None,
) -> ComplianceEvidenceListResponse:
    query = select(ComplianceEvidence)
    count_query = select(func.count(ComplianceEvidence.id))

    if control_id:
        query = query.where(ComplianceEvidence.control_id == control_id)
        count_query = count_query.where(ComplianceEvidence.control_id == control_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(ComplianceEvidence.created_at.desc())

    result = await db.execute(query)
    evidences = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return ComplianceEvidenceListResponse(
        items=[ComplianceEvidenceResponse.model_validate(e) for e in evidences],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ==================== 仪表盘 ====================


async def get_dashboard(
    db: AsyncSession,
) -> ComplianceDashboardResponse:
    # 策略总数
    policy_total_result = await db.execute(select(func.count(CompliancePolicy.id)))
    policy_total = policy_total_result.scalar()

    # 控制措施总数
    control_total_result = await db.execute(select(func.count(ComplianceControl.id)))
    control_total = control_total_result.scalar()

    # 通过率
    pass_result = await db.execute(
        select(func.count(ComplianceAudit.id))
        .where(ComplianceAudit.status == AuditStatus.PASS.value)
    )
    pass_count = pass_result.scalar()

    total_audit_result = await db.execute(select(func.count(ComplianceAudit.id)))
    total_audit = total_audit_result.scalar()

    control_pass_rate = (pass_count / total_audit * 100) if total_audit > 0 else 0.0

    # 待审计数（next_test_due 已过或未来7天内到期）
    now = datetime.now()
    upcoming = now + timedelta(days=7)
    pending_result = await db.execute(
        select(func.count(ComplianceControl.id))
        .where(
            or_(
                ComplianceControl.next_test_due <= upcoming,
                ComplianceControl.next_test_due == None,
            )
        )
    )
    audits_pending = pending_result.scalar()

    # 风险分布
    risk_dist = {}
    for level in [RiskLevel.LOW.value, RiskLevel.MEDIUM.value, RiskLevel.HIGH.value]:
        count_result = await db.execute(
            select(func.count(ComplianceControl.id)).where(ComplianceControl.risk_level == level)
        )
        risk_dist[level] = count_result.scalar()

    # 实施状态分布
    impl_dist = {}
    for status in [
        ControlImplementationStatus.NOT_IMPLEMENTED.value,
        ControlImplementationStatus.PARTIALLY_IMPLEMENTED.value,
        ControlImplementationStatus.IMPLEMENTED.value,
        ControlImplementationStatus.NOT_APPLICABLE.value,
    ]:
        count_result = await db.execute(
            select(func.count(ComplianceControl.id)).where(ComplianceControl.implementation_status == status)
        )
        impl_dist[status] = count_result.scalar()

    # 审计状态分布
    audit_dist = {}
    for status in [AuditStatus.PASS.value, AuditStatus.FAIL.value, AuditStatus.PARTIAL.value]:
        count_result = await db.execute(
            select(func.count(ComplianceAudit.id)).where(ComplianceAudit.status == status)
        )
        audit_dist[status] = count_result.scalar()

    # 即将到期的审计
    upcoming_result = await db.execute(
        select(ComplianceControl)
        .where(
            and_(
                ComplianceControl.next_test_due <= upcoming,
                ComplianceControl.next_test_due >= now,
            )
        )
        .order_by(ComplianceControl.next_test_due.asc())
        .limit(5)
    )
    upcoming_audits = []
    for ctrl in upcoming_result.scalars().all():
        upcoming_audits.append({
            "control_id": ctrl.id,
            "control_code": ctrl.control_code,
            "title": ctrl.title,
            "next_test_due": ctrl.next_test_due.isoformat() if ctrl.next_test_due else None,
            "risk_level": ctrl.risk_level,
        })

    # 最近的审计
    recent_result = await db.execute(
        select(ComplianceAudit)
        .order_by(ComplianceAudit.conducted_at.desc().nullslast())
        .limit(5)
    )
    recent_audits = []
    for a in recent_result.scalars().all():
        recent_audits.append({
            "audit_id": a.id,
            "control_id": a.control_id,
            "status": a.status,
            "audit_type": a.audit_type,
            "conducted_at": a.conducted_at.isoformat() if a.conducted_at else None,
        })

    return ComplianceDashboardResponse(
        policy_total=policy_total,
        control_total=control_total,
        control_pass_rate=round(control_pass_rate, 2),
        audits_pending=audits_pending,
        risk_distribution=risk_dist,
        implementation_status_distribution=impl_dist,
        audit_status_distribution=audit_dist,
        upcoming_audits=upcoming_audits,
        recent_audits=recent_audits,
    )


# ==================== 报告 ====================


async def get_summary_report(
    db: AsyncSession,
    period_start: date | None = None,
    period_end: date | None = None,
) -> ComplianceSummaryReportResponse:
    now = datetime.now()

    if not period_start:
        period_start = (now - timedelta(days=90)).date()
    if not period_end:
        period_end = now.date()

    # 策略摘要
    policy_result = await db.execute(
        select(CompliancePolicy).order_by(CompliancePolicy.created_at.desc())
    )
    policies = policy_result.scalars().all()

    policy_summary = []
    for p in policies:
        control_count_result = await db.execute(
            select(func.count(ComplianceControl.id)).where(ComplianceControl.policy_id == p.id)
        )
        policy_summary.append({
            "id": p.id,
            "title": p.title,
            "category": p.category,
            "status": p.status,
            "version": p.version,
            "control_count": control_count_result.scalar(),
        })

    # 控制措施摘要
    control_result = await db.execute(
        select(ComplianceControl).order_by(ComplianceControl.risk_level.desc())
    )
    controls = control_result.scalars().all()

    control_summary = []
    for c in controls:
        audit_count_result = await db.execute(
            select(func.count(ComplianceAudit.id)).where(ComplianceAudit.control_id == c.id)
        )
        latest_audit_result = await db.execute(
            select(ComplianceAudit)
            .where(ComplianceAudit.control_id == c.id)
            .order_by(ComplianceAudit.conducted_at.desc().nullslast())
            .limit(1)
        )
        latest_audit = latest_audit_result.scalar_one_or_none()

        control_summary.append({
            "id": c.id,
            "control_code": c.control_code,
            "title": c.title,
            "risk_level": c.risk_level,
            "implementation_status": c.implementation_status,
            "audit_count": audit_count_result.scalar(),
            "latest_audit_status": latest_audit.status if latest_audit else None,
            "latest_audit_date": latest_audit.conducted_at.isoformat() if latest_audit and latest_audit.conducted_at else None,
        })

    # 审计摘要
    audit_result = await db.execute(
        select(ComplianceAudit)
        .where(
            and_(
                ComplianceAudit.conducted_at >= datetime.combine(period_start, datetime.min.time()),
                ComplianceAudit.conducted_at <= datetime.combine(period_end, datetime.max.time()),
            )
        )
        .order_by(ComplianceAudit.conducted_at.desc())
    )
    audits = audit_result.scalars().all()

    audit_summary = []
    for a in audits:
        audit_summary.append({
            "id": a.id,
            "control_id": a.control_id,
            "audit_type": a.audit_type,
            "status": a.status,
            "findings": a.findings,
            "conducted_at": a.conducted_at.isoformat() if a.conducted_at else None,
        })

    # 生成建议
    recommendations = []
    high_risk_not_impl = [c for c in controls if c.risk_level == RiskLevel.HIGH.value and c.implementation_status == ControlImplementationStatus.NOT_IMPLEMENTED.value]
    if high_risk_not_impl:
        recommendations.append(f"有 {len(high_risk_not_impl)} 个高风险控制措施尚未实施，建议优先处理")

    overdue = [c for c in controls if c.next_test_due and c.next_test_due < now]
    if overdue:
        recommendations.append(f"有 {len(overdue)} 个控制措施已逾期未测试，建议尽快安排审计")

    failed_audits = [a for a in audits if a.status == AuditStatus.FAIL.value]
    if failed_audits:
        recommendations.append(f"报告期内发现 {len(failed_audits)} 项审计失败，需要整改")

    if not recommendations:
        recommendations.append("当前合规状况良好，请继续保持")

    summary = {
        "total_policies": len(policies),
        "total_controls": len(controls),
        "total_audits_in_period": len(audits),
        "pass_rate": round((sum(1 for a in audits if a.status == AuditStatus.PASS.value) / len(audits) * 100), 2) if audits else 0,
        "high_risk_controls": sum(1 for c in controls if c.risk_level == RiskLevel.HIGH.value),
        "overdue_tests": len(overdue),
    }

    return ComplianceSummaryReportResponse(
        generated_at=now,
        period_start=period_start,
        period_end=period_end,
        summary=summary,
        policy_summary=policy_summary,
        control_summary=control_summary,
        audit_summary=audit_summary,
        recommendations=recommendations,
    )

"""
PMI中国AI项目管理社区 - 审批流程API

[PMBOK KA: 整合管理 | PG: 监控 (Integration/Monitoring) — 审批流、变更审批]
对应PMI第6版标准：审批流、变更审批

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: Trustworthy AI — AI治理审批流]"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import User
from app.models.approval import (
    ApprovalFlow, ApprovalInstance, ApprovalStep, ApprovalDelegate,
    ApprovalStatus, StepStatus
)
from app.schemas.approval import (
    ApprovalFlowCreate, ApprovalFlowUpdate, ApprovalFlowResponse,
    ApprovalInstanceCreate, ApprovalInstanceResponse,
    ApprovalStepResponse, ApprovalActionRequest, ApprovalTransferRequest,
    ApprovalDelegateCreate, ApprovalDelegateUpdate, ApprovalDelegateResponse,
    ApprovalDashboardResponse
)
from app.schemas import SuccessResponse
from app.services.approval_engine import ApprovalEngine
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

router = APIRouter()


# ==================== 流程定义CRUD ====================

@router.post("/flows", response_model=ApprovalFlowResponse, status_code=201)
async def create_flow(
    flow_in: ApprovalFlowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    flow = ApprovalFlow(
        name=flow_in.name,
        description=flow_in.description,
        entity_type=flow_in.entity_type,
        steps=[s.model_dump() for s in flow_in.steps],
        is_active=flow_in.is_active,
        created_by=current_user.id,
    )
    db.add(flow)
    await db.commit()
    await db.refresh(flow)
    return flow


@router.get("/flows", response_model=List[ApprovalFlowResponse])
async def list_flows(
    entity_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(ApprovalFlow)
    conditions = []

    if entity_type:
        conditions.append(ApprovalFlow.entity_type == entity_type)
    if is_active is not None:
        conditions.append(ApprovalFlow.is_active == is_active)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(ApprovalFlow.created_at.desc())
    result = await db.execute(query)
    flows = result.scalars().all()
    return flows


@router.get("/flows/{flow_id}", response_model=ApprovalFlowResponse)
async def get_flow(
    flow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalFlow).where(ApprovalFlow.id == flow_id)
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise NotFoundException(message="审批流程不存在")
    return flow


@router.put("/flows/{flow_id}", response_model=ApprovalFlowResponse)
async def update_flow(
    flow_id: str,
    flow_in: ApprovalFlowUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalFlow).where(ApprovalFlow.id == flow_id)
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise NotFoundException(message="审批流程不存在")

    update_data = flow_in.model_dump(exclude_unset=True)
    if "steps" in update_data and update_data["steps"] is not None:
        update_data["steps"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in update_data["steps"]]

    for k, v in update_data.items():
        setattr(flow, k, v)

    flow.updated_at = datetime.now()
    await db.commit()
    await db.refresh(flow)
    return flow


@router.delete("/flows/{flow_id}", response_model=SuccessResponse)
async def delete_flow(
    flow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalFlow).where(ApprovalFlow.id == flow_id)
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise NotFoundException(message="审批流程不存在")

    await db.delete(flow)
    await db.commit()
    return SuccessResponse(message="审批流程删除成功")


@router.post("/flows/{flow_id}/activate", response_model=ApprovalFlowResponse)
async def activate_flow(
    flow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalFlow).where(ApprovalFlow.id == flow_id)
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise NotFoundException(message="审批流程不存在")

    flow.is_active = True
    flow.updated_at = datetime.now()
    await db.commit()
    await db.refresh(flow)
    return flow


@router.post("/flows/{flow_id}/deactivate", response_model=ApprovalFlowResponse)
async def deactivate_flow(
    flow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalFlow).where(ApprovalFlow.id == flow_id)
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise NotFoundException(message="审批流程不存在")

    flow.is_active = False
    flow.updated_at = datetime.now()
    await db.commit()
    await db.refresh(flow)
    return flow


# ==================== 审批请求 ====================

@router.post("/requests", response_model=ApprovalInstanceResponse, status_code=201)
async def create_request(
    request_in: ApprovalInstanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    engine = ApprovalEngine(db)
    instance = await engine.start_approval(
        flow_id=request_in.flow_id,
        entity_type=request_in.entity_type,
        entity_id=request_in.entity_id,
        requester_id=current_user.id,
    )
    return instance


@router.get("/requests", response_model=List[ApprovalInstanceResponse])
async def list_my_requests(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(ApprovalInstance).where(
        ApprovalInstance.requester_id == current_user.id
    )

    if status:
        query = query.where(ApprovalInstance.status == status)

    query = query.order_by(ApprovalInstance.created_at.desc())
    result = await db.execute(query)
    instances = result.scalars().all()
    return instances


@router.get("/requests/{instance_id}", response_model=ApprovalInstanceResponse)
async def get_request(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalInstance).where(ApprovalInstance.id == instance_id)
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundException(message="审批实例不存在")
    return instance


# ==================== 待审批列表 ====================

@router.get("/pending", response_model=List[ApprovalInstanceResponse])
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalInstance)
        .join(ApprovalStep, ApprovalInstance.id == ApprovalStep.instance_id)
        .where(
            ApprovalStep.approver_id == current_user.id,
            ApprovalStep.status == StepStatus.PENDING.value,
            ApprovalInstance.status == ApprovalStatus.PENDING.value
        )
        .order_by(ApprovalInstance.created_at.desc())
        .distinct()
    )
    instances = result.scalars().all()
    return instances


# ==================== 审批操作 ====================

@router.post("/steps/{step_id}/approve", response_model=ApprovalInstanceResponse)
async def approve_step(
    step_id: str,
    action_in: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    engine = ApprovalEngine(db)
    instance = await engine.process_step(
        step_id=step_id,
        approver_id=current_user.id,
        action=StepStatus.APPROVED.value,
        comment=action_in.comment
    )
    return instance


@router.post("/steps/{step_id}/reject", response_model=ApprovalInstanceResponse)
async def reject_step(
    step_id: str,
    action_in: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    engine = ApprovalEngine(db)
    instance = await engine.process_step(
        step_id=step_id,
        approver_id=current_user.id,
        action=StepStatus.REJECTED.value,
        comment=action_in.comment
    )
    return instance


@router.post("/steps/{step_id}/transfer", response_model=ApprovalStepResponse)
async def transfer_step(
    step_id: str,
    transfer_in: ApprovalTransferRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    engine = ApprovalEngine(db)
    new_step = await engine.transfer_step(
        step_id=step_id,
        from_approver_id=current_user.id,
        to_approver_id=transfer_in.transfer_to,
        comment=transfer_in.comment
    )
    return new_step


# ==================== 已处理列表 ====================

@router.get("/processed", response_model=List[ApprovalInstanceResponse])
async def list_processed_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalInstance)
        .join(ApprovalStep, ApprovalInstance.id == ApprovalStep.instance_id)
        .where(
            ApprovalStep.approver_id == current_user.id,
            ApprovalStep.status.in_([StepStatus.APPROVED.value, StepStatus.REJECTED.value])
        )
        .order_by(ApprovalInstance.created_at.desc())
        .distinct()
    )
    instances = result.scalars().all()
    return instances


# ==================== 审批仪表盘 ====================

@router.get("/dashboard", response_model=ApprovalDashboardResponse)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    engine = ApprovalEngine(db)
    stats = await engine.get_dashboard_stats(current_user.id)
    return ApprovalDashboardResponse(**stats)


# ==================== 委托管理 ====================

@router.post("/delegates", response_model=ApprovalDelegateResponse, status_code=201)
async def create_delegate(
    delegate_in: ApprovalDelegateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    delegate = ApprovalDelegate(
        delegator_id=current_user.id,
        delegatee_id=delegate_in.delegatee_id,
        start_date=delegate_in.start_date,
        end_date=delegate_in.end_date,
        is_active=delegate_in.is_active,
    )
    db.add(delegate)
    await db.commit()
    await db.refresh(delegate)
    return delegate


@router.get("/delegates", response_model=List[ApprovalDelegateResponse])
async def list_delegates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalDelegate)
        .where(ApprovalDelegate.delegator_id == current_user.id)
        .order_by(ApprovalDelegate.created_at.desc())
    )
    delegates = result.scalars().all()
    return delegates


@router.put("/delegates/{delegate_id}", response_model=ApprovalDelegateResponse)
async def update_delegate(
    delegate_id: str,
    delegate_in: ApprovalDelegateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalDelegate).where(
            ApprovalDelegate.id == delegate_id,
            ApprovalDelegate.delegator_id == current_user.id
        )
    )
    delegate = result.scalar_one_or_none()
    if not delegate:
        raise NotFoundException(message="委托不存在")

    update_data = delegate_in.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(delegate, k, v)

    await db.commit()
    await db.refresh(delegate)
    return delegate


@router.delete("/delegates/{delegate_id}", response_model=SuccessResponse)
async def delete_delegate(
    delegate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ApprovalDelegate).where(
            ApprovalDelegate.id == delegate_id,
            ApprovalDelegate.delegator_id == current_user.id
        )
    )
    delegate = result.scalar_one_or_none()
    if not delegate:
        raise NotFoundException(message="委托不存在")

    await db.delete(delegate)
    await db.commit()
    return SuccessResponse(message="委托删除成功")

"""
PMI中国AI项目管理社区 - 预算 CRUD 路由

[PMBOK KA: 成本管理 (Cost Management) — 预算制定、EVM成本基准、成本估算与控制]
对应PMI第6版标准：成本估算、预算制定、EVM成本基准
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

from app.db.session import get_db
from app.models import ProjectBudget, BudgetCategory, CostRecord, Project, User
from app.schemas.budget import (
    BudgetCreate, BudgetUpdate, BudgetResponse,
)
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user
from app.api.v1.budgets.helpers import _to_float, _calc_budget_response

budget_router = APIRouter()


@budget_router.post("/projects/{project_id}/budget", response_model=BudgetResponse, status_code=201)
async def create_budget(
    project_id: str,
    budget_in: BudgetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 检查项目是否存在
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise NotFoundException(message="项目不存在")

    # 检查是否已有预算
    existing_result = await db.execute(
        select(ProjectBudget).where(ProjectBudget.project_id == project_id)
    )
    if existing_result.scalar_one_or_none():
        raise ValidationException(message="该项目已存在预算")

    budget = ProjectBudget(
        project_id=project_id,
        total_budget=budget_in.total_budget,
        currency=budget_in.currency,
        labor_rate=budget_in.labor_rate,
        overhead_rate=budget_in.overhead_rate,
        start_date=budget_in.start_date,
        end_date=budget_in.end_date,
        status="active",
        created_by=current_user.id,
    )
    db.add(budget)
    await db.commit()
    await db.refresh(budget)

    resp = BudgetResponse.model_validate(budget)
    resp_dict = resp.model_dump()
    resp_dict.update(_calc_budget_response(budget, 0))
    return BudgetResponse(**resp_dict)


@budget_router.get("/projects/{project_id}/budget", response_model=BudgetResponse)
async def get_project_budget(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ProjectBudget).where(ProjectBudget.project_id == project_id)
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise NotFoundException(message="项目预算不存在")

    # 计算总花费
    spent_result = await db.execute(
        select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
            CostRecord.budget_id == budget.id
        )
    )
    total_spent = _to_float(spent_result.scalar())

    resp = BudgetResponse.model_validate(budget)
    resp_dict = resp.model_dump()
    resp_dict.update(_calc_budget_response(budget, total_spent))
    return BudgetResponse(**resp_dict)


@budget_router.get("/budgets/{budget_id}", response_model=BudgetResponse)
async def get_budget(
    budget_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ProjectBudget).where(ProjectBudget.id == budget_id)
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise NotFoundException(message="预算不存在")

    spent_result = await db.execute(
        select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
            CostRecord.budget_id == budget.id
        )
    )
    total_spent = _to_float(spent_result.scalar())

    resp = BudgetResponse.model_validate(budget)
    resp_dict = resp.model_dump()
    resp_dict.update(_calc_budget_response(budget, total_spent))
    return BudgetResponse(**resp_dict)


@budget_router.put("/budgets/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: str,
    budget_in: BudgetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ProjectBudget).where(ProjectBudget.id == budget_id)
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise NotFoundException(message="预算不存在")

    update_data = budget_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(budget, field, value)

    budget.updated_at = datetime.now()
    await db.commit()
    await db.refresh(budget)

    spent_result = await db.execute(
        select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
            CostRecord.budget_id == budget.id
        )
    )
    total_spent = _to_float(spent_result.scalar())

    resp = BudgetResponse.model_validate(budget)
    resp_dict = resp.model_dump()
    resp_dict.update(_calc_budget_response(budget, total_spent))
    return BudgetResponse(**resp_dict)


@budget_router.delete("/budgets/{budget_id}")
async def delete_budget(
    budget_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ProjectBudget).where(ProjectBudget.id == budget_id)
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise NotFoundException(message="预算不存在")

    await db.delete(budget)
    await db.commit()
    return {"success": True, "message": "预算删除成功"}

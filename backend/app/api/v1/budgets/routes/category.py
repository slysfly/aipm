"""
PMI中国AI项目管理社区 - 预算分类 CRUD 路由
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from datetime import datetime

from app.db.session import get_db
from app.models import ProjectBudget, BudgetCategory, User
from app.schemas.budget import (
    BudgetCategoryCreate, BudgetCategoryUpdate, BudgetCategoryResponse,
)
from app.core.exceptions import NotFoundException
from app.core.security import get_current_user
from app.api.v1.budgets.helpers import _calc_category_response

category_router = APIRouter()


@category_router.get("/budgets/{budget_id}/categories", response_model=List[BudgetCategoryResponse])
async def list_categories(
    budget_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(BudgetCategory).where(BudgetCategory.budget_id == budget_id)
    )
    categories = result.scalars().all()

    responses = []
    for cat in categories:
        resp = BudgetCategoryResponse.model_validate(cat)
        resp_dict = resp.model_dump()
        resp_dict.update(_calc_category_response(cat))
        responses.append(BudgetCategoryResponse(**resp_dict))
    return responses


@category_router.post("/budgets/{budget_id}/categories", response_model=BudgetCategoryResponse, status_code=201)
async def create_category(
    budget_id: str,
    category_in: BudgetCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    budget_result = await db.execute(
        select(ProjectBudget).where(ProjectBudget.id == budget_id)
    )
    if not budget_result.scalar_one_or_none():
        raise NotFoundException(message="预算不存在")

    category = BudgetCategory(
        budget_id=budget_id,
        name=category_in.name,
        allocated_amount=category_in.allocated_amount,
        description=category_in.description,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)

    resp = BudgetCategoryResponse.model_validate(category)
    resp_dict = resp.model_dump()
    resp_dict.update(_calc_category_response(category))
    return BudgetCategoryResponse(**resp_dict)


@category_router.get("/budgets/categories/{category_id}", response_model=BudgetCategoryResponse)
async def get_category(
    category_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(BudgetCategory).where(BudgetCategory.id == category_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise NotFoundException(message="预算分类不存在")

    resp = BudgetCategoryResponse.model_validate(category)
    resp_dict = resp.model_dump()
    resp_dict.update(_calc_category_response(category))
    return BudgetCategoryResponse(**resp_dict)


@category_router.put("/budgets/categories/{category_id}", response_model=BudgetCategoryResponse)
async def update_category(
    category_id: str,
    category_in: BudgetCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(BudgetCategory).where(BudgetCategory.id == category_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise NotFoundException(message="预算分类不存在")

    update_data = category_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    category.updated_at = datetime.now()
    await db.commit()
    await db.refresh(category)

    resp = BudgetCategoryResponse.model_validate(category)
    resp_dict = resp.model_dump()
    resp_dict.update(_calc_category_response(category))
    return BudgetCategoryResponse(**resp_dict)


@category_router.delete("/budgets/categories/{category_id}")
async def delete_category(
    category_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(BudgetCategory).where(BudgetCategory.id == category_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise NotFoundException(message="预算分类不存在")

    await db.delete(category)
    await db.commit()
    return {"success": True, "message": "预算分类删除成功"}

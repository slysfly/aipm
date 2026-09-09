"""
PMI中国AI项目管理社区 - 成本记录 CRUD 路由
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional

from app.db.session import get_db
from app.models import ProjectBudget, BudgetCategory, CostRecord, Project, Task, User
from app.schemas.budget import (
    CostRecordCreate, CostRecordUpdate, CostRecordResponse, CostRecordListResponse,
)
from app.core.exceptions import NotFoundException
from app.core.security import get_current_user
from app.api.v1.budgets.helpers import _to_float

cost_record_router = APIRouter()


@cost_record_router.get("/projects/{project_id}/costs", response_model=CostRecordListResponse)
async def list_cost_records(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    cost_type: Optional[str] = None,
    category_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(CostRecord).where(CostRecord.project_id == project_id)
    count_query = select(func.count(CostRecord.id)).where(CostRecord.project_id == project_id)

    if cost_type:
        query = query.where(CostRecord.cost_type == cost_type)
        count_query = count_query.where(CostRecord.cost_type == cost_type)

    if category_id:
        query = query.where(CostRecord.category_id == category_id)
        count_query = count_query.where(CostRecord.category_id == category_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(CostRecord.recorded_at.desc())

    result = await db.execute(query)
    records = result.scalars().all()

    # 加载关联数据
    responses = []
    for record in records:
        resp = CostRecordResponse.model_validate(record)
        resp_dict = resp.model_dump()

        # 获取任务名称
        if record.task_id:
            task_result = await db.execute(
                select(Task.name).where(Task.id == record.task_id)
            )
            resp_dict["task_name"] = task_result.scalar()

        # 获取记录人名称
        if record.recorded_by:
            user_result = await db.execute(
                select(User.username).where(User.id == record.recorded_by)
            )
            resp_dict["recorder_name"] = user_result.scalar()

        # 获取分类名称
        if record.category_id:
            cat_result = await db.execute(
                select(BudgetCategory.name).where(BudgetCategory.id == record.category_id)
            )
            resp_dict["category_name"] = cat_result.scalar()

        responses.append(CostRecordResponse(**resp_dict))

    total_pages = (total + page_size - 1) // page_size
    return CostRecordListResponse(
        items=responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@cost_record_router.post("/projects/{project_id}/costs", response_model=CostRecordResponse, status_code=201)
async def create_cost_record(
    project_id: str,
    cost_in: CostRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 验证项目
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )
    if not project_result.scalar_one_or_none():
        raise NotFoundException(message="项目不存在")

    # 验证预算
    budget_result = await db.execute(
        select(ProjectBudget).where(ProjectBudget.id == cost_in.budget_id)
    )
    budget = budget_result.scalar_one_or_none()
    if not budget:
        raise NotFoundException(message="预算不存在")

    # 人工成本自动计算
    amount = cost_in.amount
    labor_rate_at_record = 0
    if cost_in.cost_type == "labor" and cost_in.work_hours and cost_in.work_hours > 0:
        labor_rate_at_record = _to_float(budget.labor_rate)
        amount = labor_rate_at_record * cost_in.work_hours

    record = CostRecord(
        project_id=project_id,
        budget_id=cost_in.budget_id,
        category_id=cost_in.category_id,
        task_id=cost_in.task_id,
        cost_type=cost_in.cost_type,
        amount=amount,
        description=cost_in.description,
        recorded_by=current_user.id,
        receipt_url=cost_in.receipt_url,
        work_hours=cost_in.work_hours or 0,
        labor_rate_at_record=labor_rate_at_record,
    )
    db.add(record)

    # 更新分类已花费金额
    if cost_in.category_id:
        cat_result = await db.execute(
            select(BudgetCategory).where(BudgetCategory.id == cost_in.category_id)
        )
        category = cat_result.scalar_one_or_none()
        if category:
            category.spent_amount = _to_float(category.spent_amount) + amount

    await db.commit()
    await db.refresh(record)

    resp = CostRecordResponse.model_validate(record)
    resp_dict = resp.model_dump()

    # 加载关联名称
    if record.task_id:
        task_result = await db.execute(select(Task.name).where(Task.id == record.task_id))
        resp_dict["task_name"] = task_result.scalar()
    resp_dict["recorder_name"] = current_user.username
    if record.category_id:
        cat_result = await db.execute(
            select(BudgetCategory.name).where(BudgetCategory.id == record.category_id)
        )
        resp_dict["category_name"] = cat_result.scalar()

    return CostRecordResponse(**resp_dict)


@cost_record_router.get("/costs/{cost_id}", response_model=CostRecordResponse)
async def get_cost_record(
    cost_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(CostRecord).where(CostRecord.id == cost_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise NotFoundException(message="成本记录不存在")

    resp = CostRecordResponse.model_validate(record)
    resp_dict = resp.model_dump()

    if record.task_id:
        task_result = await db.execute(select(Task.name).where(Task.id == record.task_id))
        resp_dict["task_name"] = task_result.scalar()
    if record.recorded_by:
        user_result = await db.execute(
            select(User.username).where(User.id == record.recorded_by)
        )
        resp_dict["recorder_name"] = user_result.scalar()
    if record.category_id:
        cat_result = await db.execute(
            select(BudgetCategory.name).where(BudgetCategory.id == record.category_id)
        )
        resp_dict["category_name"] = cat_result.scalar()

    return CostRecordResponse(**resp_dict)


@cost_record_router.put("/costs/{cost_id}", response_model=CostRecordResponse)
async def update_cost_record(
    cost_id: str,
    cost_in: CostRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(CostRecord).where(CostRecord.id == cost_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise NotFoundException(message="成本记录不存在")

    old_amount = _to_float(record.amount)
    old_category_id = record.category_id

    update_data = cost_in.model_dump(exclude_unset=True)

    # 人工成本重新计算
    if record.cost_type == "labor" or update_data.get("cost_type") == "labor":
        work_hours = update_data.get("work_hours", record.work_hours)
        if work_hours and work_hours > 0:
            budget_result = await db.execute(
                select(ProjectBudget).where(ProjectBudget.id == record.budget_id)
            )
            budget = budget_result.scalar_one_or_none()
            if budget:
                labor_rate = _to_float(budget.labor_rate)
                update_data["amount"] = labor_rate * work_hours
                update_data["labor_rate_at_record"] = labor_rate

    for field, value in update_data.items():
        setattr(record, field, value)

    await db.commit()
    await db.refresh(record)

    # 更新分类金额（如果金额或分类变化）
    new_amount = _to_float(record.amount)
    new_category_id = record.category_id

    if old_category_id and old_category_id == new_category_id and old_amount != new_amount:
        diff = new_amount - old_amount
        cat_result = await db.execute(
            select(BudgetCategory).where(BudgetCategory.id == old_category_id)
        )
        category = cat_result.scalar_one_or_none()
        if category:
            category.spent_amount = _to_float(category.spent_amount) + diff
    elif old_category_id != new_category_id:
        if old_category_id:
            cat_result = await db.execute(
                select(BudgetCategory).where(BudgetCategory.id == old_category_id)
            )
            category = cat_result.scalar_one_or_none()
            if category:
                category.spent_amount = _to_float(category.spent_amount) - old_amount
        if new_category_id:
            cat_result = await db.execute(
                select(BudgetCategory).where(BudgetCategory.id == new_category_id)
            )
            category = cat_result.scalar_one_or_none()
            if category:
                category.spent_amount = _to_float(category.spent_amount) + new_amount

    await db.commit()

    resp = CostRecordResponse.model_validate(record)
    resp_dict = resp.model_dump()

    if record.task_id:
        task_result = await db.execute(select(Task.name).where(Task.id == record.task_id))
        resp_dict["task_name"] = task_result.scalar()
    if record.recorded_by:
        user_result = await db.execute(
            select(User.username).where(User.id == record.recorded_by)
        )
        resp_dict["recorder_name"] = user_result.scalar()
    if record.category_id:
        cat_result = await db.execute(
            select(BudgetCategory.name).where(BudgetCategory.id == record.category_id)
        )
        resp_dict["category_name"] = cat_result.scalar()

    return CostRecordResponse(**resp_dict)


@cost_record_router.delete("/costs/{cost_id}")
async def delete_cost_record(
    cost_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(CostRecord).where(CostRecord.id == cost_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise NotFoundException(message="成本记录不存在")

    # 更新分类已花费金额
    if record.category_id:
        cat_result = await db.execute(
            select(BudgetCategory).where(BudgetCategory.id == record.category_id)
        )
        category = cat_result.scalar_one_or_none()
        if category:
            category.spent_amount = _to_float(category.spent_amount) - _to_float(record.amount)

    await db.delete(record)
    await db.commit()
    return {"success": True, "message": "成本记录删除成功"}

"""
PMI中国AI项目管理社区 - 预算/成本跟踪 API路由

[PMBOK KA: 成本管理 (Cost Management) — 预算制定、EVM成本基准、成本估算与控制]
对应PMI第6版标准：成本估算、预算制定、EVM成本基准

PMBOK 7th Principle: Value | Domain: Measurement — 聚焦价值、成本测量
PMBOK 8th: Real-Time Financial Intelligence"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, extract
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal

from app.db.session import get_db
from app.models import (
    ProjectBudget, BudgetCategory, CostRecord,
    Project, Task, User
)
from app.schemas.budget import (
    BudgetCreate, BudgetUpdate, BudgetResponse,
    BudgetCategoryCreate, BudgetCategoryUpdate, BudgetCategoryResponse,
    CostRecordCreate, CostRecordUpdate, CostRecordResponse, CostRecordListResponse,
    BudgetReportResponse, BudgetTrendResponse, BudgetTrendItem,
    BudgetOverviewResponse
)
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

router = APIRouter()


# ==================== 辅助函数 ====================

def _to_float(value) -> float:
    return float(value) if value is not None else 0.0


def _calc_budget_response(budget: ProjectBudget, total_spent: float = 0) -> dict:
    total = _to_float(budget.total_budget)
    remaining = total - total_spent
    execution_rate = (total_spent / total * 100) if total > 0 else 0
    return {
        "total_spent": total_spent,
        "total_remaining": remaining,
        "execution_rate": round(execution_rate, 2),
        "is_over_budget": total_spent > total,
    }


def _calc_category_response(category: BudgetCategory) -> dict:
    allocated = _to_float(category.allocated_amount)
    spent = _to_float(category.spent_amount)
    remaining = allocated - spent
    execution_rate = (spent / allocated * 100) if allocated > 0 else 0
    return {
        "remaining": remaining,
        "execution_rate": round(execution_rate, 2),
        "is_over_budget": spent > allocated,
    }


# ==================== 项目预算 CRUD ====================

@router.post("/projects/{project_id}/budget", response_model=BudgetResponse, status_code=201)
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


@router.get("/projects/{project_id}/budget", response_model=BudgetResponse)
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


@router.get("/budgets/{budget_id}", response_model=BudgetResponse)
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


@router.put("/budgets/{budget_id}", response_model=BudgetResponse)
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


@router.delete("/budgets/{budget_id}")
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


# ==================== 预算分类 ====================

@router.get("/budgets/{budget_id}/categories", response_model=List[BudgetCategoryResponse])
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


@router.post("/budgets/{budget_id}/categories", response_model=BudgetCategoryResponse, status_code=201)
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


@router.get("/budgets/categories/{category_id}", response_model=BudgetCategoryResponse)
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


@router.put("/budgets/categories/{category_id}", response_model=BudgetCategoryResponse)
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


@router.delete("/budgets/categories/{category_id}")
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


# ==================== 成本记录 ====================

@router.get("/projects/{project_id}/costs", response_model=CostRecordListResponse)
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

    result = await db.execute(
        query.options(
            selectinload(CostRecord.task),
            selectinload(CostRecord.recorder),
            selectinload(CostRecord.category),
        )
    )
    records = result.scalars().all()

    # 关联数据已通过 selectinload 预加载，无需逐条查询（消除 N+1）
    responses = []
    for record in records:
        resp = CostRecordResponse.model_validate(record)
        resp_dict = resp.model_dump()
        resp_dict["task_name"] = record.task.name if record.task else None
        resp_dict["recorder_name"] = record.recorder.username if record.recorder else None
        resp_dict["category_name"] = record.category.name if record.category else None
        responses.append(CostRecordResponse(**resp_dict))

    total_pages = (total + page_size - 1) // page_size
    return CostRecordListResponse(
        items=responses,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.post("/projects/{project_id}/costs", response_model=CostRecordResponse, status_code=201)
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


@router.get("/costs/{cost_id}", response_model=CostRecordResponse)
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


@router.put("/costs/{cost_id}", response_model=CostRecordResponse)
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


@router.delete("/costs/{cost_id}")
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


# ==================== 预算报告与趋势 ====================

@router.get("/projects/{project_id}/budget/report", response_model=BudgetReportResponse)
async def get_budget_report(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 获取预算
    budget_result = await db.execute(
        select(ProjectBudget).where(ProjectBudget.project_id == project_id)
    )
    budget = budget_result.scalar_one_or_none()

    if not budget:
        return BudgetReportResponse(project_id=project_id)

    total_budget = _to_float(budget.total_budget)
    currency = budget.currency

    # 总花费
    spent_result = await db.execute(
        select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
            CostRecord.budget_id == budget.id
        )
    )
    total_spent = _to_float(spent_result.scalar())

    # 按类型统计
    type_stats_result = await db.execute(
        select(CostRecord.cost_type, func.coalesce(func.sum(CostRecord.amount), 0))
        .where(CostRecord.budget_id == budget.id)
        .group_by(CostRecord.cost_type)
    )
    cost_by_type = {row[0]: _to_float(row[1]) for row in type_stats_result.all()}

    # 按分类统计
    cat_stats_result = await db.execute(
        select(
            BudgetCategory.id,
            BudgetCategory.name,
            BudgetCategory.allocated_amount,
            BudgetCategory.spent_amount,
        ).where(BudgetCategory.budget_id == budget.id)
    )
    cost_by_category = []
    for row in cat_stats_result.all():
        allocated = _to_float(row[2])
        spent = _to_float(row[3])
        cost_by_category.append({
            "id": row[0],
            "name": row[1],
            "allocated": allocated,
            "spent": spent,
            "remaining": allocated - spent,
            "execution_rate": round((spent / allocated * 100), 2) if allocated > 0 else 0,
        })

    # 人工成本统计
    labor_result = await db.execute(
        select(
            func.coalesce(func.sum(CostRecord.work_hours), 0),
            func.coalesce(func.sum(CostRecord.amount), 0),
        ).where(
            CostRecord.budget_id == budget.id,
            CostRecord.cost_type == "labor"
        )
    )
    labor_row = labor_result.one()
    total_labor_hours = _to_float(labor_row[0])
    total_labor_cost = _to_float(labor_row[1])

    # 预警信息
    alerts = []
    if total_spent > total_budget:
        alerts.append(f"预算已超支！超支金额: {total_spent - total_budget:.2f} {currency}")
    elif total_spent > total_budget * 0.9:
        alerts.append(f"预算即将耗尽！已使用 {total_spent / total_budget * 100:.1f}%")

    for cat in cost_by_category:
        if cat["spent"] > cat["allocated"] and cat["allocated"] > 0:
            alerts.append(f"分类 [{cat['name']}] 已超支")

    return BudgetReportResponse(
        project_id=project_id,
        budget_id=budget.id,
        total_budget=total_budget,
        total_spent=total_spent,
        total_remaining=total_budget - total_spent,
        execution_rate=round((total_spent / total_budget * 100), 2) if total_budget > 0 else 0,
        currency=currency,
        is_over_budget=total_spent > total_budget,
        cost_by_type=cost_by_type,
        cost_by_category=cost_by_category,
        alerts=alerts,
        total_labor_hours=total_labor_hours,
        total_labor_cost=total_labor_cost,
    )


@router.get("/projects/{project_id}/budget/trend", response_model=BudgetTrendResponse)
async def get_budget_trend(
    project_id: str,
    months: int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    budget_result = await db.execute(
        select(ProjectBudget).where(ProjectBudget.project_id == project_id)
    )
    budget = budget_result.scalar_one_or_none()

    if not budget:
        return BudgetTrendResponse(project_id=project_id)

    currency = budget.currency

    # 按月统计成本
    monthly_result = await db.execute(
        select(
            extract('year', CostRecord.recorded_at).label('year'),
            extract('month', CostRecord.recorded_at).label('month'),
            CostRecord.cost_type,
            func.coalesce(func.sum(CostRecord.amount), 0).label('total'),
        )
        .where(
            CostRecord.project_id == project_id,
        )
        .group_by(
            extract('year', CostRecord.recorded_at),
            extract('month', CostRecord.recorded_at),
            CostRecord.cost_type,
        )
        .order_by('year', 'month')
    )

    # 整理数据
    monthly_data = {}
    for row in monthly_result.all():
        year = int(row[0])
        month = int(row[1])
        cost_type = row[2]
        amount = _to_float(row[3])
        key = f"{year}-{month:02d}"
        if key not in monthly_data:
            monthly_data[key] = {
                "year": year,
                "month": month,
                "labor_cost": 0,
                "material_cost": 0,
                "overhead_cost": 0,
                "travel_cost": 0,
                "other_cost": 0,
            }
        field_map = {
            "labor": "labor_cost",
            "material": "material_cost",
            "overhead": "overhead_cost",
            "travel": "travel_cost",
            "other": "other_cost",
        }
        field = field_map.get(cost_type, "other_cost")
        monthly_data[key][field] = amount

    # 构建趋势列表
    trend_items = []
    cumulative = 0
    for key in sorted(monthly_data.keys()):
        data = monthly_data[key]
        total = (
            data["labor_cost"] + data["material_cost"] +
            data["overhead_cost"] + data["travel_cost"] + data["other_cost"]
        )
        cumulative += total
        trend_items.append(BudgetTrendItem(
            month=key,
            year=data["year"],
            month_num=data["month"],
            labor_cost=data["labor_cost"],
            material_cost=data["material_cost"],
            overhead_cost=data["overhead_cost"],
            travel_cost=data["travel_cost"],
            other_cost=data["other_cost"],
            total_cost=total,
            cumulative_cost=cumulative,
        ))

    # 限制返回月份数
    if len(trend_items) > months:
        trend_items = trend_items[-months:]

    return BudgetTrendResponse(
        project_id=project_id,
        currency=currency,
        data=trend_items,
    )


# ==================== 预算概览 ====================

@router.get("/projects/{project_id}/budget/overview", response_model=BudgetOverviewResponse)
async def get_budget_overview(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    budget_result = await db.execute(
        select(ProjectBudget).where(ProjectBudget.project_id == project_id)
    )
    budget = budget_result.scalar_one_or_none()

    if not budget:
        return BudgetOverviewResponse(project_id=project_id, has_budget=False)

    # 总花费
    spent_result = await db.execute(
        select(func.coalesce(func.sum(CostRecord.amount), 0)).where(
            CostRecord.budget_id == budget.id
        )
    )
    total_spent = _to_float(spent_result.scalar())

    # 预算响应
    budget_resp = BudgetResponse.model_validate(budget)
    budget_dict = budget_resp.model_dump()
    budget_dict.update(_calc_budget_response(budget, total_spent))

    # 分类
    cat_result = await db.execute(
        select(BudgetCategory).where(BudgetCategory.budget_id == budget.id)
    )
    categories = cat_result.scalars().all()
    cat_responses = []
    for cat in categories:
        resp = BudgetCategoryResponse.model_validate(cat)
        resp_dict = resp.model_dump()
        resp_dict.update(_calc_category_response(cat))
        cat_responses.append(BudgetCategoryResponse(**resp_dict))

    # 最近成本记录
    recent_result = await db.execute(
        select(CostRecord)
        .where(CostRecord.project_id == project_id)
        .order_by(CostRecord.recorded_at.desc())
        .limit(5)
    )
    recent_records = recent_result.scalars().all()
    recent_costs = []
    for record in recent_records:
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
            cat_result2 = await db.execute(
                select(BudgetCategory.name).where(BudgetCategory.id == record.category_id)
            )
            resp_dict["category_name"] = cat_result2.scalar()
        recent_costs.append(CostRecordResponse(**resp_dict))

    # 总记录数
    count_result = await db.execute(
        select(func.count(CostRecord.id)).where(CostRecord.project_id == project_id)
    )
    total_cost_records = count_result.scalar()

    return BudgetOverviewResponse(
        project_id=project_id,
        has_budget=True,
        budget=BudgetResponse(**budget_dict),
        categories=cat_responses,
        recent_costs=recent_costs,
        total_cost_records=total_cost_records,
    )

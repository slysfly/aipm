"""
PMI中国AI项目管理社区 - 预算服务层

存放预算报表、趋势、概览等业务逻辑。
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, extract
from sqlalchemy.orm import selectinload
from typing import List

from app.models import ProjectBudget, BudgetCategory, CostRecord, Task, User
from app.schemas.budget import (
    BudgetResponse,
    BudgetCategoryResponse,
    CostRecordResponse,
    BudgetReportResponse,
    BudgetTrendResponse,
    BudgetTrendItem,
    BudgetOverviewResponse,
)
from app.api.v1.budgets.helpers import _to_float, _calc_budget_response, _calc_category_response


async def get_budget_report(
    project_id: str,
    db: AsyncSession,
) -> BudgetReportResponse:
    """获取项目预算报告"""
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


async def get_budget_trend(
    project_id: str,
    months: int = 12,
    db: AsyncSession = None,
) -> BudgetTrendResponse:
    """获取预算趋势"""
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


async def get_budget_overview(
    project_id: str,
    db: AsyncSession,
) -> BudgetOverviewResponse:
    """获取预算概览"""
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
        .options(
            selectinload(CostRecord.task),
            selectinload(CostRecord.recorder),
            selectinload(CostRecord.category),
        )
    )
    recent_records = recent_result.scalars().all()
    recent_costs = []
    for record in recent_records:
        resp = CostRecordResponse.model_validate(record)
        resp_dict = resp.model_dump()
        resp_dict["task_name"] = record.task.name if record.task else None
        resp_dict["recorder_name"] = record.recorder.username if record.recorder else None
        resp_dict["category_name"] = record.category.name if record.category else None
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

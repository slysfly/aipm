"""
PMI中国AI项目管理社区 - 预算/成本跟踪 API路由

[PMBOK KA: 成本管理 (Cost Management) — 预算制定、EVM成本基准、成本估算与控制]
对应PMI第6版标准：成本估算、预算制定、EVM成本基准

PMBOK 7th Principle: Value | Domain: Measurement — 聚焦价值、成本测量
PMBOK 8th: Real-Time Financial Intelligence

从 budgets.py 拆分为包结构后的主入口模块。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_db
from app.models import User
from app.core.security import get_current_user

from app.api.v1.budgets.routes.budget import budget_router
from app.api.v1.budgets.routes.category import category_router
from app.api.v1.budgets.routes.cost_record import cost_record_router

# 预算报告、趋势、概览路由（使用 services/budget_service.py）
from app.services.budget_service import (
    get_budget_report as _get_budget_report,
    get_budget_trend as _get_budget_trend,
    get_budget_overview as _get_budget_overview,
)
from app.schemas.budget import (
    BudgetReportResponse,
    BudgetTrendResponse,
    BudgetOverviewResponse,
)

router = APIRouter()

# 包含子路由
router.include_router(budget_router)
router.include_router(category_router)
router.include_router(cost_record_router)


# ==================== 预算报告与趋势（使用服务层） ====================

@router.get("/projects/{project_id}/budget/report", response_model=BudgetReportResponse)
async def get_budget_report(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await _get_budget_report(project_id=project_id, db=db)


@router.get("/projects/{project_id}/budget/trend", response_model=BudgetTrendResponse)
async def get_budget_trend(
    project_id: str,
    months: int = Query(12, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await _get_budget_trend(project_id=project_id, months=months, db=db)


@router.get("/projects/{project_id}/budget/overview", response_model=BudgetOverviewResponse)
async def get_budget_overview(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await _get_budget_overview(project_id=project_id, db=db)

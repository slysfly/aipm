"""
PMI中国AI项目管理社区 - AI预测分析API路由

[PMBOK KA: 风险管理 (Risk) — AI风险预测、风险趋势分析]
对应PMI第6版标准：AI风险预测、风险趋势分析

[CPMAI Phase: CPMAI Phase: Model Evaluation | Domain: Machine Learning — AI预测模型评估]
PMBOK 7th Principle: Risk/Uncertainty | Domain: Uncertainty — 预测分析、不确定性应对
PMBOK 8th: Predictive AI Analytics"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from app.db.session import get_db
from app.models import User
from app.core.security import get_current_user
from app.services.ai.predictive_analytics import PredictiveAnalytics

router = APIRouter()


@router.get("/projects/{project_id}/health")
async def get_project_health(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    analytics = PredictiveAnalytics(db)
    result = await analytics.analyze_project_health(project_id)
    return result


@router.get("/projects/{project_id}/completion")
async def predict_project_completion(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    analytics = PredictiveAnalytics(db)
    result = await analytics.predict_completion_date(project_id)
    return result


@router.get("/sprints/{sprint_id}/risk")
async def analyze_sprint_risk(
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    analytics = PredictiveAnalytics(db)
    result = await analytics.analyze_sprint_risk(sprint_id)
    return result


@router.get("/dashboard")
async def get_risk_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    analytics = PredictiveAnalytics(db)
    result = await analytics.get_global_risk_dashboard()
    return result

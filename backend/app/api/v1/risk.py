"""
风险登记册 API（复用 Risk 模型）

[PMBOK KA: 风险管理 (Risk Management) — 风险识别、定性/定量分析、风险应对、风险登记册]
对应PMI第6版标准：风险识别、定性分析、定量分析、风险应对

PMBOK 7th Principle: Risk/Optimize Risk Responses | Domain: Uncertainty — 风险识别、优化应对
PMBOK 8th: AI-Powered Risk Analytics"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User, Risk

router = APIRouter(prefix="/risks", tags=["风险登记册"])


class RiskCreate(BaseModel):
    project_id: str  # 必须关联项目
    name: str
    description: Optional[str] = None
    category: Optional[str] = "technical"
    probability: float = 0.5
    impact: float = 0.5
    status: Optional[str] = "identified"
    owner_id: Optional[str] = None
    trigger_condition: Optional[str] = None
    response_strategy: Optional[str] = None
    response_plan: Optional[str] = None
    response_cost: float = 0


class RiskUpdate(BaseModel):
    project_id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    probability: Optional[float] = None
    impact: Optional[float] = None
    status: Optional[str] = None
    owner_id: Optional[str] = None
    trigger_condition: Optional[str] = None
    response_strategy: Optional[str] = None
    response_plan: Optional[str] = None
    response_cost: Optional[float] = None


def _risk_to_dict(r: Risk) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "name": r.name,
        "description": r.description,
        "category": r.category,
        "probability": float(r.probability) if r.probability is not None else 0.5,
        "impact": float(r.impact) if r.impact is not None else 0.5,
        "risk_score": float(r.risk_score) if r.risk_score is not None else 0.0,
        "trigger_condition": r.trigger_condition,
        "status": r.status,
        "owner_id": r.owner_id,
        "response_strategy": r.response_strategy,
        "response_plan": r.response_plan,
        "response_cost": float(r.response_cost) if r.response_cost is not None else 0.0,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


@router.get("")
async def list_risks(
    project_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Risk)
    if project_id:
        q = q.where(Risk.project_id == project_id)
    q = q.order_by(desc(Risk.created_at))
    res = await db.execute(q)
    return [_risk_to_dict(r) for r in res.scalars().all()]


@router.post("", status_code=201)
async def create_risk(payload: RiskCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    d = payload.model_dump()
    d["risk_score"] = round(float(d.get("probability", 0.5)) * float(d.get("impact", 0.5)), 4)
    obj = Risk(**d)
    db.add(obj)
    await db.flush()
    return _risk_to_dict(obj)


@router.get("/{risk_id}")
async def get_risk(risk_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    obj = await db.get(Risk, risk_id)
    if not obj:
        raise HTTPException(404, "风险不存在")
    return _risk_to_dict(obj)


@router.put("/{risk_id}")
async def update_risk(risk_id: str, payload: RiskUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    obj = await db.get(Risk, risk_id)
    if not obj:
        raise HTTPException(404, "风险不存在")
    data = payload.model_dump(exclude_unset=True)
    if data.get("probability") is not None and data.get("impact") is not None:
        obj.risk_score = round(float(data["probability"]) * float(data["impact"]), 4)
    for k, v in data.items():
        if v is not None:
            setattr(obj, k, v)
    await db.flush()
    return _risk_to_dict(obj)


@router.delete("/{risk_id}")
async def delete_risk(risk_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    obj = await db.get(Risk, risk_id)
    if not obj:
        raise HTTPException(404, "风险不存在")
    await db.delete(obj)
    return {"ok": True}

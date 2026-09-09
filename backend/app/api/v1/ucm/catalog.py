"""用户管理子系统 - 套餐 / 功能 / 单项开通 API"""
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.ucm import Organization, Feature, Plan, PlanFeature, UserFeatureGrant
from app.api.v1.ucm.deps import require_ucm_admin, require_org_access

router = APIRouter()


def feature_to_dict(f: Feature) -> dict:
    return {"id": f.id, "code": f.code, "name": f.name, "category": f.category, "is_addon": f.is_addon, "price_monthly": float(f.price_monthly) if f.price_monthly else 0}


def plan_to_dict(p: Plan) -> dict:
    return {"id": p.id, "code": p.code, "name": p.name, "price_monthly": float(p.price_monthly) if p.price_monthly else 0,
            "price_yearly": float(p.price_yearly) if p.price_yearly else 0, "max_seats": p.max_seats,
            "description": p.description, "is_active": p.is_active}


# ── 功能模块 ─────────────────────────────────────────────────
@router.get("/features")
async def list_features(user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Feature))
    return [feature_to_dict(f) for f in res.scalars().all()]


@router.post("/features")
async def create_feature(payload: dict, user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    if not payload.get("code") or not payload.get("name"):
        raise HTTPException(400, "code 和 name 必填")
    res = await db.execute(select(Feature).where(Feature.code == payload["code"]))
    if res.scalar_one_or_none():
        raise HTTPException(400, "功能编码已存在")
    f = Feature(code=payload["code"], name=payload["name"], category=payload.get("category", "general"),
                is_addon=payload.get("is_addon", False), price_monthly=payload.get("price_monthly", 0))
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return feature_to_dict(f)


# ── 套餐 ─────────────────────────────────────────────────────
@router.get("/plans")
async def list_plans(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Plan))
    return [plan_to_dict(p) for p in res.scalars().all()]


@router.post("/plans")
async def create_plan(payload: dict, user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    if not payload.get("code") or not payload.get("name"):
        raise HTTPException(400, "code 和 name 必填")
    res = await db.execute(select(Plan).where(Plan.code == payload["code"]))
    if res.scalar_one_or_none():
        raise HTTPException(400, "套餐编码已存在")
    p = Plan(code=payload["code"], name=payload["name"], price_monthly=payload.get("price_monthly", 0),
             price_yearly=payload.get("price_yearly", 0), max_seats=payload.get("max_seats", 5),
             description=payload.get("description"), is_active=payload.get("is_active", True))
    db.add(p)
    await db.flush()
    for fc in payload.get("features", []):
        fid = await _resolve_feature(db, fc)
        db.add(PlanFeature(plan_id=p.id, feature_id=fid, included=True))
    await db.commit()
    await db.refresh(p)
    return plan_to_dict(p)


async def _resolve_feature(db, code_or_id):
    res = await db.execute(select(Feature).where((Feature.code == code_or_id) | (Feature.id == code_or_id)))
    f = res.scalar_one_or_none()
    if not f:
        raise HTTPException(400, f"功能不存在: {code_or_id}")
    return f.id


@router.put("/plans/{plan_id}")
async def update_plan(plan_id: str, payload: dict, user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Plan).where(Plan.id == plan_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "套餐不存在")
    for k in ["name", "price_monthly", "price_yearly", "max_seats", "description", "is_active"]:
        if k in payload and payload[k] is not None:
            setattr(p, k, payload[k])
    if "features" in payload:
        await db.execute(text("DELETE FROM plan_features WHERE plan_id = :pid"), {"pid": plan_id})
        for fc in payload["features"]:
            fid = await _resolve_feature(db, fc)
            db.add(PlanFeature(plan_id=p.id, feature_id=fid, included=True))
    await db.commit()
    await db.refresh(p)
    return plan_to_dict(p)


# ── 组织功能开通状态 ─────────────────────────────────────────
@router.get("/organizations/{org_id}/grants")
async def get_grants(org_id: str, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Organization).where(Organization.id == org_id))
    org = res.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "组织不存在")
    plan_features = {}
    if org.plan_id:
        res = await db.execute(select(PlanFeature, Feature).join(Feature, Feature.id == PlanFeature.feature_id).where(PlanFeature.plan_id == org.plan_id))
        for pf, f in res.all():
            plan_features[f.code] = pf.included
    grants = {}
    res = await db.execute(select(UserFeatureGrant, Feature).join(Feature, Feature.id == UserFeatureGrant.feature_id).where(UserFeatureGrant.org_id == org_id))
    for g, f in res.all():
        if g.expire_at and g.expire_at < datetime.now():
            continue
        grants[f.code] = g.expire_at.isoformat() if g.expire_at else None
    res = await db.execute(select(Feature))
    out = []
    for f in res.scalars().all():
        plan_inc = plan_features.get(f.code, False)
        grant_exp = grants.get(f.code)
        active = plan_inc or grant_exp is not None
        out.append({
            "code": f.code, "name": f.name, "category": f.category, "is_addon": f.is_addon,
            "active": active, "source": "grant" if grant_exp is not None else ("plan" if plan_inc else None),
            "expire_at": grant_exp,
        })
    return out


@router.post("/organizations/{org_id}/grants")
async def grant_feature(org_id: str, payload: dict, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    feature_code = payload.get("feature_code")
    if not feature_code:
        raise HTTPException(400, "feature_code 必填")
    fid = await _resolve_feature(db, feature_code)
    expire_at = None
    if payload.get("expire_at"):
        expire_at = datetime.fromisoformat(payload["expire_at"])
    g = UserFeatureGrant(org_id=org_id, feature_id=fid, granted_by=user.id, expire_at=expire_at, reason=payload.get("reason"))
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return {"granted": feature_code, "expire_at": g.expire_at.isoformat() if g.expire_at else None}


@router.delete("/organizations/{org_id}/grants/{feature_code}")
async def revoke_feature(org_id: str, feature_code: str, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Feature).where(Feature.code == feature_code))
    f = res.scalar_one_or_none()
    if not f:
        raise HTTPException(404, "功能不存在")
    await db.execute(text("DELETE FROM user_feature_grants WHERE org_id = :oid AND feature_id = :fid"), {"oid": org_id, "fid": f.id})
    await db.commit()
    return {"revoked": feature_code}

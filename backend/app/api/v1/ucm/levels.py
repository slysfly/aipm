"""用户管理子系统 - 用户等级 API"""
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.ucm import UserLevel, UserLevelRecord
from app.api.v1.ucm.deps import require_ucm_admin

router = APIRouter()


def level_to_dict(l: UserLevel) -> dict:
    return {"id": l.id, "code": l.code, "name": l.name, "min_points": l.min_points, "benefits": l.benefits, "icon": l.icon}


@router.get("/user-levels")
async def list_levels(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(UserLevel).order_by(UserLevel.min_points))
    return [level_to_dict(l) for l in res.scalars().all()]


@router.post("/user-levels")
async def create_level(payload: dict, user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    if not payload.get("code") or not payload.get("name"):
        raise HTTPException(400, "code 和 name 必填")
    res = await db.execute(select(UserLevel).where(UserLevel.code == payload["code"]))
    if res.scalar_one_or_none():
        raise HTTPException(400, "等级编码已存在")
    l = UserLevel(code=payload["code"], name=payload["name"], min_points=payload.get("min_points", 0),
                  benefits=payload.get("benefits"), icon=payload.get("icon"))
    db.add(l)
    await db.commit()
    await db.refresh(l)
    return level_to_dict(l)


@router.get("/users/{user_id}/level")
async def get_user_level(user_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.id != user_id and not user.is_superuser:
        raise HTTPException(403, "权限不足")
    res = await db.execute(select(User).where(User.id == user_id))
    u = res.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "用户不存在")
    res = await db.execute(select(UserLevel).where(UserLevel.code == u.level_code))
    lv = res.scalar_one_or_none()
    return {"user_id": u.id, "level_code": u.level_code, "level_points": u.level_points,
            "level_name": lv.name if lv else u.level_code}


@router.post("/users/{user_id}/level")
async def set_user_level(user_id: str, payload: dict, user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    """手动调整用户等级（自动记录变更日志）"""
    to_code = payload.get("level_code")
    if not to_code:
        raise HTTPException(400, "level_code 必填")
    res = await db.execute(select(User).where(User.id == user_id))
    u = res.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "用户不存在")
    res = await db.execute(select(UserLevel).where(UserLevel.code == to_code))
    if not res.scalar_one_or_none():
        raise HTTPException(400, "目标等级不存在")
    from_code = u.level_code
    u.level_code = to_code
    db.add(UserLevelRecord(user_id=user_id, from_level=from_code, to_level=to_code, reason=payload.get("reason", "manual"), operator=user.id))
    await db.commit()
    return {"user_id": user_id, "from": from_code, "to": to_code}


@router.get("/users/{user_id}/level-records")
async def level_records(user_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.id != user_id and not user.is_superuser:
        raise HTTPException(403, "权限不足")
    res = await db.execute(select(UserLevelRecord).where(UserLevelRecord.user_id == user_id).order_by(UserLevelRecord.created_at.desc()))
    out = []
    for r in res.scalars().all():
        out.append({"id": r.id, "from_level": r.from_level, "to_level": r.to_level, "reason": r.reason,
                    "created_at": r.created_at.isoformat() if r.created_at else None})
    return out

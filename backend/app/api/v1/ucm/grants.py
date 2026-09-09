"""用户管理子系统 - 管理权限开通
三档管理权限：
  - super_admin  系统管理：可操作系统全部功能（含整个运营管理板块）
  - admin        用户管理：可管理用户、用户级别、功能开通（不能操作系统级配置）
  - user         普通用户：仅可使用除运营管理板块外的功能

三档互斥：同一个用户只能是其中一档。切换角色即把 is_superuser / is_org_admin 同步更新。
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.api.v1.ucm.deps import require_ucm_admin

router = APIRouter()


VALID_ROLES = ("super_admin", "admin", "user")


def _role_of(u: User) -> str:
    if u.is_superuser:
        return "super_admin"
    if u.is_org_admin:
        return "admin"
    return "user"


def _apply_role(u: User, role: str) -> None:
    """三档互斥：写入 is_superuser / is_org_admin"""
    u.is_superuser = (role == "super_admin")
    u.is_org_admin = (role == "admin")
    # role=user 时两者均为 False，无需额外处理


@router.get("/grants/users")
async def list_admin_users(
    user: User = Depends(require_ucm_admin),
    db: AsyncSession = Depends(get_db),
    q: str | None = None,
    skip: int = 0,
    limit: int = 500,
):
    """列出全部用户及其当前管理角色
    仅 superuser 可访问
    """
    stmt = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = select(User).where(
            (User.username.ilike(like))
            | (User.full_name.ilike(like))
            | (User.email.ilike(like))
        ).order_by(User.created_at.desc()).offset(skip).limit(limit)
    res = await db.execute(stmt)
    users = res.scalars().all()
    out = []
    for u in users:
        out.append({
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "email": u.email,
            "is_active": bool(u.is_active),
            "organization_id": u.organization_id,
            "role": _role_of(u),
            "is_superuser": bool(u.is_superuser),
            "is_org_admin": bool(u.is_org_admin),
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })
    return {"items": out, "total": len(out)}


class SetRoleBody(BaseModel):
    role: str  # super_admin | admin | user
    reason: str | None = None  # 备注


@router.post("/grants/users/{user_id}/set-role")
async def set_user_role(
    user_id: str,
    body: SetRoleBody,
    operator: User = Depends(require_ucm_admin),
    db: AsyncSession = Depends(get_db),
):
    """给指定用户设置管理角色（三档互斥）"""
    # 管理权限开通仅系统管理员可执行：依赖 require_ucm_admin 已保证 operator 为 super，
    # 此处显式兜底，防止未来依赖被放宽导致越权提权/降级
    if not operator.is_superuser:
        raise HTTPException(status_code=403, detail="管理权限开通仅系统管理员可执行")
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"role 必须是 {VALID_ROLES} 之一")

    res = await db.execute(select(User).where(User.id == user_id))
    target = res.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 防止最后一个 super_admin 把自己降级
    if body.role != "super_admin" and target.is_superuser:
        cnt_res = await db.execute(
            select(User).where(User.is_superuser == True)  # noqa: E712
        )
        super_cnt = len(cnt_res.scalars().all())
        if super_cnt <= 1:
            raise HTTPException(
                status_code=400,
                detail="系统至少保留一位系统管理员，无法降级最后一位 super_admin",
            )

    prev_role = _role_of(target)
    _apply_role(target, body.role)
    new_role = _role_of(target)
    await db.commit()
    await db.refresh(target)

    return {
        "ok": True,
        "user_id": target.id,
        "username": target.username,
        "prev_role": prev_role,
        "new_role": new_role,
        "is_superuser": bool(target.is_superuser),
        "is_org_admin": bool(target.is_org_admin),
        "operator_id": operator.id,
        "operator_username": operator.username,
        "reason": body.reason,
        "changed_at": datetime.now(timezone.utc).isoformat(),
    }

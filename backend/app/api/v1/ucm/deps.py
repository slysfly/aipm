"""用户管理子系统 - 权限依赖"""
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.ucm import UserOrganization


async def require_ucm_admin(user: User = Depends(get_current_user)) -> User:
    """平台管理员（superuser）才能操作系统级用户管理"""
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足，需要平台管理员权限")
    return user


async def require_org_access(org_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> User:
    """组织管理员或平台管理员可操作本组织"""
    if user.is_superuser:
        return user
    res = await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == user.id,
            UserOrganization.org_id == org_id,
            UserOrganization.role_in_org.in_(["org_admin", "dept_manager"]),
        )
    )
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足，需要该组织管理员权限")
    return user

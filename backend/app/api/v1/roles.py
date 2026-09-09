"""
[PMBOK KA: 资源管理 (Resource) — 角色定义、权限分配、RACI矩阵]
对应PMI第6版标准：角色定义、RACI矩阵、团队职责分配
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.session import get_db
from app.core.security import get_current_user, require_superuser
from app.models import User
from app.models.permission import Role, Permission

router = APIRouter(prefix="/roles", tags=["角色管理"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_role(
    name: str,
    description: Optional[str] = None,
    permissions: List[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_superuser)
):
    if permissions is None:
        permissions = []

    result = await db.execute(
        select(Role).where(Role.name == name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="角色名称已存在"
        )

    role = Role(
        name=name,
        description=description,
        permissions=permissions,
        is_system=False
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@router.get("/")
async def list_roles(
    is_system: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Role)
    if is_system is not None:
        query = query.where(Role.is_system == is_system)

    count_query = select(Role)
    if is_system is not None:
        count_query = count_query.where(Role.is_system == is_system)

    total_result = await db.execute(count_query)
    total = len(total_result.scalars().all())

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    roles = result.scalars().all()

    return {
        "items": roles,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/{role_id}")
async def get_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Role).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )
    return role


@router.put("/{role_id}")
async def update_role(
    role_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    permissions: Optional[List[str]] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_superuser)
):
    result = await db.execute(
        select(Role).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="系统角色不可修改"
        )

    if name:
        result = await db.execute(
            select(Role).where(
                and_(Role.name == name, Role.id != role_id)
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="角色名称已存在"
            )
        role.name = name

    if description is not None:
        role.description = description

    if permissions is not None:
        role.permissions = permissions

    await db.commit()
    await db.refresh(role)
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_superuser)
):
    result = await db.execute(
        select(Role).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="角色不存在"
        )

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="系统角色不可删除"
        )

    await db.delete(role)
    await db.commit()


@router.get("/permissions/all")
async def list_permissions(
    current_user: User = Depends(get_current_user)
):
    return [
        {"value": p.value, "label": p.value.replace(".", " ").title()}
        for p in Permission
    ]

"""
[PMBOK KA: 资源管理/相关方管理 (Resource/Stakeholder) — 团队管理、干系人参与]
对应PMI第6版标准：项目团队组建、干系人识别与参与
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.session import get_db
from app.core.security import get_current_user
from app.core.permissions import check_project_permission, Permission
from app.models import User
from app.models.permission import ProjectMember, Role

router = APIRouter(prefix="/projects/{project_id}/members", tags=["项目成员管理"])


async def get_project_member(
    db: AsyncSession,
    project_id: str,
    user_id: str
) -> Optional[ProjectMember]:
    result = await db.execute(
        select(ProjectMember)
        .where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_active == True
            )
        )
    )
    return result.scalar_one_or_none()


@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_member(
    project_id: str,
    user_id: str,
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    has_perm = await check_project_permission(
        db, current_user.id, project_id, Permission.MEMBER_INVITE
    )
    if not has_perm and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要邀请成员权限"
        )

    result = await db.execute(
        select(Role).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="角色不存在"
        )

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户不存在"
        )

    existing = await get_project_member(db, project_id, user_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已是项目成员"
        )

    member = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role_id=role_id,
        invited_by=current_user.id,
        is_active=True
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.get("/")
async def list_members(
    project_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ProjectMember)
        .where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.is_active == True
            )
        )
    )
    members = result.scalars().all()

    total = len(members)
    start = (page - 1) * page_size
    end = start + page_size
    items = members[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/{user_id}")
async def get_member(
    project_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    member = await get_project_member(db, project_id, user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="成员不存在"
        )
    return member


@router.put("/{user_id}")
async def update_member_role(
    project_id: str,
    user_id: str,
    role_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    has_perm = await check_project_permission(
        db, current_user.id, project_id, Permission.MEMBER_INVITE
    )
    if not has_perm and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要成员管理权限"
        )

    result = await db.execute(
        select(Role).where(Role.id == role_id)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="角色不存在"
        )

    member = await get_project_member(db, project_id, user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="成员不存在"
        )

    member.role_id = role_id
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    project_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    has_perm = await check_project_permission(
        db, current_user.id, project_id, Permission.MEMBER_REMOVE
    )
    if not has_perm and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要移除成员权限"
        )

    member = await get_project_member(db, project_id, user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="成员不存在"
        )

    if member.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能移除自己"
        )

    member.is_active = False
    await db.commit()


@router.get("/{user_id}/permissions")
async def get_member_permissions(
    project_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if user_id != current_user.id and not current_user.is_superuser:
        has_perm = await check_project_permission(
            db, current_user.id, project_id, Permission.SETTINGS_VIEW
        )
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )

    member = await get_project_member(db, project_id, user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="成员不存在"
        )

    return {
        "user_id": user_id,
        "project_id": project_id,
        "role_id": member.role_id,
        "role_name": member.role.name if member.role else None,
        "permissions": member.role.permissions if member.role else []
    }

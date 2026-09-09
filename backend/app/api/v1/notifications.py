"""
[PMBOK KA: 沟通管理 (Communications) — 信息分发、干系人通知]
对应PMI第6版标准：沟通需求、信息分发
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import datetime

from app.db.session import get_db
from app.models import Notification, User
from app.schemas import (
    NotificationResponse, NotificationListResponse,
    UnreadCountResponse, SuccessResponse
)
from app.core.exceptions import NotFoundException
from app.core.security import get_current_user

router = APIRouter()


@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Notification).where(Notification.user_id == current_user.id)
    count_query = select(func.count(Notification.id)).where(
        Notification.user_id == current_user.id
    )

    if unread_only:
        query = query.where(Notification.is_read == False)
        count_query = count_query.where(Notification.is_read == False)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(
        Notification.created_at.desc()
    )

    result = await db.execute(query)
    notifications = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.put("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise NotFoundException(message="通知不存在")

    notification.is_read = True
    notification.read_at = datetime.now()

    await db.commit()
    await db.refresh(notification)

    return notification


@router.put("/read-all", response_model=SuccessResponse)
async def mark_all_as_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False
        )
    )
    notifications = result.scalars().all()

    for notification in notifications:
        notification.is_read = True
        notification.read_at = datetime.now()

    await db.commit()

    return SuccessResponse(message="全部通知已标记为已读")


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False
        )
    )
    count = result.scalar()

    return UnreadCountResponse(count=count)


@router.delete("/{notification_id}", response_model=SuccessResponse)
async def delete_notification(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise NotFoundException(message="通知不存在")

    await db.delete(notification)
    await db.commit()

    return SuccessResponse(message="通知删除成功")

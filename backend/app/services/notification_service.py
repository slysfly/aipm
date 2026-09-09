from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional

from app.models import Notification, User


async def create_notification(
    db: AsyncSession,
    user_id: str,
    type: str,
    title: str,
    content: Optional[str] = None,
    related_type: Optional[str] = None,
    related_id: Optional[str] = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        content=content,
        related_type=related_type,
        related_id=related_id,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return notification


async def notify_mention(
    db: AsyncSession,
    sender_id: str,
    sender_name: str,
    target_username: str,
    comment_id: str,
    task_id: str,
    content: str,
) -> Optional[Notification]:
    result = await db.execute(
        select(User).where(User.username == target_username)
    )
    target_user = result.scalar_one_or_none()

    if not target_user or target_user.id == sender_id:
        return None

    return await create_notification(
        db=db,
        user_id=target_user.id,
        type="mention",
        title=f"{sender_name} 在评论中@了你",
        content=content[:200],
        related_type="comment",
        related_id=comment_id,
    )


async def notify_task_assigned(
    db: AsyncSession,
    task_name: str,
    assignee_id: str,
    task_id: str,
    assigned_by_name: str,
) -> Optional[Notification]:
    return await create_notification(
        db=db,
        user_id=assignee_id,
        type="assign",
        title=f"{assigned_by_name} 将任务分配给你",
        content=f"任务: {task_name}",
        related_type="task",
        related_id=task_id,
    )


async def notify_status_change(
    db: AsyncSession,
    task_name: str,
    old_status: str,
    new_status: str,
    user_id: str,
    task_id: str,
) -> Optional[Notification]:
    return await create_notification(
        db=db,
        user_id=user_id,
        type="status_change",
        title=f"任务状态变更: {task_name}",
        content=f"状态从 {old_status} 变更为 {new_status}",
        related_type="task",
        related_id=task_id,
    )


async def notify_due_soon(
    db: AsyncSession,
    task_name: str,
    user_id: str,
    task_id: str,
    days_left: int,
) -> Optional[Notification]:
    return await create_notification(
        db=db,
        user_id=user_id,
        type="due_soon",
        title=f"任务即将到期: {task_name}",
        content=f"还剩 {days_left} 天",
        related_type="task",
        related_id=task_id,
    )


async def notify_risk_alert(
    db: AsyncSession,
    risk_name: str,
    user_id: str,
    risk_id: str,
    project_id: str,
    alert_level: str = "high",
) -> Optional[Notification]:
    return await create_notification(
        db=db,
        user_id=user_id,
        type="risk_alert",
        title=f"风险预警: {risk_name}",
        content=f"预警级别: {alert_level}",
        related_type="risk",
        related_id=risk_id,
    )

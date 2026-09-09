"""
[PMBOK KA: 沟通管理 | PG: 执行 (Communications/Executing) — 任务评论、沟通记录]
对应PMI第6版标准：沟通记录、任务评论
"""

import re
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import Comment, Task, User, Project
from app.schemas import (
    CommentCreate, CommentUpdate, CommentResponse, CommentListResponse,
    SuccessResponse
)
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user
from app.services.notification_service import notify_mention
from app.services.webhook_service import trigger_webhook_event
from app.schemas.webhook import WebhookEvent
from app.services.zapier_integration import notify_zapier_event, ZapierEventType
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

MENTION_PATTERN = re.compile(r"@([a-zA-Z0-9_\u4e00-\u9fa5]+)")


def extract_mentions(content: str) -> List[str]:
    return MENTION_PATTERN.findall(content)


async def get_comment_or_404(db: AsyncSession, comment_id: str) -> Comment:
    result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.is_deleted == False)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise NotFoundException(message="评论不存在")
    return comment


async def build_comment_tree(
    db: AsyncSession,
    comments: List[Comment],
    parent_id: Optional[str] = None
) -> List[CommentResponse]:
    tree = []
    for comment in comments:
        if (comment.parent_id == parent_id) or (parent_id is None and comment.parent_id is None):
            reply_tree = await build_comment_tree(db, comments, comment.id)
            comment_data = CommentResponse.model_validate(comment)
            comment_data.replies = reply_tree
            tree.append(comment_data)
    return tree


@router.post("/tasks/{task_id}/comments", response_model=CommentResponse, status_code=201)
async def create_comment(
    task_id: str,
    comment_in: CommentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.is_deleted == False)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundException(message="任务不存在")

    mentions = extract_mentions(comment_in.content)

    comment = Comment(
        content=comment_in.content,
        task_id=task_id,
        project_id=comment_in.project_id or task.project_id,
        user_id=current_user.id,
        parent_id=comment_in.parent_id,
        mentions=mentions,
    )

    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    for username in mentions:
        background_tasks.add_task(
            notify_mention,
            db=db,
            sender_id=current_user.id,
            sender_name=current_user.username or current_user.full_name,
            target_username=username,
            comment_id=comment.id,
            task_id=task_id,
            content=comment_in.content,
        )

    # 触发 Webhook（评论创建）与 Zapier（打通外部系统数据）
    try:
        payload = {
            "event": "comment.created",
            "data": {
                "id": comment.id,
                "content": comment.content,
                "task_id": task_id,
                "project_id": comment.project_id,
                "user_id": current_user.id,
            },
            "timestamp": comment.created_at.isoformat() if comment.created_at else None,
        }
        await trigger_webhook_event(db, WebhookEvent.COMMENT_CREATED, payload, project_id=comment.project_id)
        await notify_zapier_event(ZapierEventType.COMMENT_ADDED, payload["data"])
    except Exception as e:
        logger.warning(f"评论事件触发失败: {e}")

    # 重新查询并预加载关系，避免异步上下文下序列化时触发懒加载（MissingGreenlet 500）
    result = await db.execute(
        select(Comment)
        .options(
            selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.replies).selectinload(Comment.user),
        )
        .where(Comment.id == comment.id)
    )
    return result.scalar_one()


@router.get("/tasks/{task_id}/comments", response_model=CommentListResponse)
async def list_comments(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.is_deleted == False)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundException(message="任务不存在")

    count_query = select(func.count(Comment.id)).where(
        Comment.task_id == task_id,
        Comment.is_deleted == False
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = (
        select(Comment)
        .options(
            selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.replies).selectinload(Comment.user),
        )
        .where(
            Comment.task_id == task_id,
            Comment.is_deleted == False,
        )
        .order_by(Comment.created_at.asc())
    )

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    comments = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    comment_list = []
    for comment in comments:
        comment_data = CommentResponse.model_validate(comment)
        if comment.user:
            from app.schemas.comment import CommentUserInfo
            comment_data.user = CommentUserInfo(
                id=comment.user.id,
                username=comment.user.username,
                full_name=comment.user.full_name,
                avatar_url=comment.user.avatar_url,
            )
        comment_list.append(comment_data)

    return CommentListResponse(
        items=comment_list,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.put("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: str,
    comment_in: CommentUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    comment = await get_comment_or_404(db, comment_id)

    if comment.user_id != current_user.id and not current_user.is_superuser:
        raise ValidationException(message="无权修改此评论")

    update_data = comment_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(comment, field, value)

    if "content" in update_data:
        comment.mentions = extract_mentions(update_data["content"])

    comment.updated_at = datetime.now()

    await db.commit()
    result = await db.execute(
        select(Comment)
        .options(
            selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.replies).selectinload(Comment.user),
        )
        .where(Comment.id == comment.id)
    )
    comment = result.scalar_one()

    for username in (comment.mentions or []):
        background_tasks.add_task(
            notify_mention,
            db=db,
            sender_id=current_user.id,
            sender_name=current_user.username or current_user.full_name,
            target_username=username,
            comment_id=comment.id,
            task_id=comment.task_id,
            content=comment.content,
        )

    return comment


@router.delete("/comments/{comment_id}", response_model=SuccessResponse)
async def delete_comment(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    comment = await get_comment_or_404(db, comment_id)

    if comment.user_id != current_user.id and not current_user.is_superuser:
        raise ValidationException(message="无权删除此评论")

    comment.is_deleted = True
    comment.updated_at = datetime.now()

    await db.commit()

    return SuccessResponse(message="评论删除成功")


@router.post("/comments/{comment_id}/reply", response_model=CommentResponse, status_code=201)
async def reply_comment(
    comment_id: str,
    comment_in: CommentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    parent = await get_comment_or_404(db, comment_id)

    result = await db.execute(
        select(Task).where(Task.id == parent.task_id, Task.is_deleted == False)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundException(message="任务不存在")

    mentions = extract_mentions(comment_in.content)

    comment = Comment(
        content=comment_in.content,
        task_id=parent.task_id,
        project_id=parent.project_id,
        user_id=current_user.id,
        parent_id=comment_id,
        mentions=mentions,
    )

    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    for username in mentions:
        background_tasks.add_task(
            notify_mention,
            db=db,
            sender_id=current_user.id,
            sender_name=current_user.username or current_user.full_name,
            target_username=username,
            comment_id=comment.id,
            task_id=parent.task_id,
            content=comment_in.content,
        )

    # 触发 Webhook 与 Zapier（回复同样打通外部系统）
    try:
        payload = {
            "event": "comment.created",
            "data": {
                "id": comment.id,
                "content": comment.content,
                "task_id": parent.task_id,
                "project_id": comment.project_id,
                "user_id": current_user.id,
                "parent_id": comment_id,
            },
            "timestamp": comment.created_at.isoformat() if comment.created_at else None,
        }
        await trigger_webhook_event(db, WebhookEvent.COMMENT_CREATED, payload, project_id=comment.project_id)
        await notify_zapier_event(ZapierEventType.COMMENT_ADDED, payload["data"])
    except Exception as e:
        logger.warning(f"评论事件触发失败: {e}")

    # 重新查询并预加载关系，避免异步上下文下序列化时触发懒加载（MissingGreenlet 500）
    result = await db.execute(
        select(Comment)
        .options(
            selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.user),
            selectinload(Comment.replies).selectinload(Comment.replies).selectinload(Comment.user),
        )
        .where(Comment.id == comment.id)
    )
    return result.scalar_one()

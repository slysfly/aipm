"""
[PMBOK KA: 沟通管理 | PG: 执行 (Communications/Executing) — Webhook通知、事件驱动]
对应PMI第6版标准：事件驱动沟通

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: AI Management — 模型运营事件驱动]"""

from typing import Optional, List
import socket

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User, ProjectMember
from app.services.webhook_service import WebhookService
from app.schemas.webhook import (
    WebhookCreate, WebhookUpdate, WebhookResponse,
    WebhookListResponse, WebhookDeliveryListResponse,
    WebhookTestRequest, WebhookTestResponse
)

router = APIRouter(prefix="/webhooks", tags=["Webhook管理"])


async def _is_webhook_visible(webhook, current_user: User, db: AsyncSession) -> bool:
    if current_user.is_superuser:
        return True
    if webhook.created_by == current_user.id:
        return True
    if webhook.project_id:
        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == webhook.project_id,
                ProjectMember.user_id == current_user.id,
                ProjectMember.is_active == True,  # noqa: E712
            )
        )
        if result.scalar_one_or_none() is not None:
            return True
    return False


@router.post("/", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    data: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = WebhookService(db)
    try:
        webhook = await service.create_webhook(
            name=data.name,
            url=str(data.url),
            events=data.events,
            created_by=current_user.id,
            project_id=data.project_id,
            secret=data.secret
        )
    except (ValueError, socket.gaierror) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return webhook


@router.get("/", response_model=WebhookListResponse)
async def list_webhooks(
    project_id: Optional[str] = Query(None),
    event: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = WebhookService(db)
    webhooks = await service.get_webhooks_by_project(
        project_id=project_id,
        event=event,
        active_only=False
    )
    if not current_user.is_superuser:
        visible = []
        for wh in webhooks:
            if await _is_webhook_visible(wh, current_user, db):
                visible.append(wh)
        webhooks = visible

    total = len(webhooks)
    start = (page - 1) * page_size
    end = start + page_size
    items = webhooks[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)
    if not webhook or not await _is_webhook_visible(webhook, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook不存在"
        )
    return webhook


@router.put("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    data: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)
    if not webhook or not await _is_webhook_visible(webhook, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook不存在"
        )

    update_data = data.model_dump(exclude_unset=True)
    if "url" in update_data and update_data["url"]:
        update_data["url"] = str(update_data["url"])

    try:
        updated = await service.update_webhook(webhook_id, **update_data)
    except (ValueError, socket.gaierror) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return updated


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)
    if not webhook or not await _is_webhook_visible(webhook, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook不存在"
        )

    success = await service.delete_webhook(webhook_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除失败"
        )


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: str,
    data: Optional[WebhookTestRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)
    if not webhook or not await _is_webhook_visible(webhook, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook不存在"
        )

    event = data.event if data else "task.created"
    payload = data.payload if data else None

    result = await service.test_webhook(webhook, event, payload)
    return WebhookTestResponse(**result)


@router.get("/{webhook_id}/deliveries", response_model=WebhookDeliveryListResponse)
async def get_webhook_deliveries(
    webhook_id: str,
    event: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = WebhookService(db)
    webhook = await service.get_webhook(webhook_id)
    if not webhook or not await _is_webhook_visible(webhook, current_user, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook不存在"
        )

    deliveries, total = await service.get_deliveries(
        webhook_id=webhook_id,
        event=event,
        success=success,
        page=page,
        page_size=page_size
    )

    return {
        "items": deliveries,
        "total": total,
        "page": page,
        "page_size": page_size
    }

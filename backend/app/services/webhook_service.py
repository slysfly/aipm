import hmac
import hashlib
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

import socket
import ipaddress
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.models.webhook import Webhook, WebhookDelivery
from app.schemas.webhook import WebhookEvent


TRUSTED_WEBHOOK_HOSTS: set = set()


def _is_non_routable(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast


def _validate_webhook_url(url):
    if not url or not isinstance(url, str):
        raise ValueError("Webhook URL 不能为空")
    p = urlparse(url)
    scheme = (p.scheme or "").lower()
    if scheme not in ("https", "http"):
        raise ValueError("Webhook URL 仅允许 http/https")
    host = (p.hostname or "").lower()
    if not host:
        raise ValueError("Webhook URL 缺少主机名")
    if scheme == "http" and host not in TRUSTED_WEBHOOK_HOSTS:
        raise ValueError("仅受信任内网主机允许 http，其余必须使用 https")
    try:
        if _is_non_routable(host):
            raise ValueError("Webhook URL 指向内网/保留地址，已拒绝")
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(host, None):
            if _is_non_routable(info[4][0]):
                raise ValueError("Webhook URL 解析到内网/保留地址，已拒绝")
    except socket.gaierror:
        # DNS 解析失败：拒绝该 webhook，不发起请求；转为 ValueError 便于上层返回 400
        raise ValueError(f"无法解析 Webhook 主机: {host}")
    except ValueError as e:
        if "内网" in str(e) or "保留" in str(e):
            raise
        raise ValueError(f"无法解析 Webhook 主机: {host}")
    return url


class WebhookService:
    MAX_RETRIES = 5
    BASE_DELAY = 1
    TIMEOUT = 30

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_webhook(self, webhook_id: str) -> Optional[Webhook]:
        result = await self.db.execute(
            select(Webhook).where(Webhook.id == webhook_id)
        )
        return result.scalar_one_or_none()

    async def get_webhooks_by_project(
        self,
        project_id: Optional[str] = None,
        event: Optional[str] = None,
        active_only: bool = True
    ) -> List[Webhook]:
        conditions = []
        if project_id:
            conditions.append(Webhook.project_id == project_id)
        if active_only:
            conditions.append(Webhook.is_active == True)

        query = select(Webhook)
        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        webhooks = result.scalars().all()

        if event:
            webhooks = [w for w in webhooks if event in (w.events or [])]

        return list(webhooks)

    async def create_webhook(
        self,
        name: str,
        url: str,
        events: List[str],
        created_by: str,
        project_id: Optional[str] = None,
        secret: Optional[str] = None
    ) -> Webhook:
        if not secret:
            secret = self._generate_secret()

        _validate_webhook_url(url)

        webhook = Webhook(
            name=name,
            url=str(url),
            secret=secret,
            events=events,
            project_id=project_id,
            created_by=created_by,
            is_active=True,
            failure_count=0,
            last_status="pending"
        )
        self.db.add(webhook)
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def update_webhook(
        self,
        webhook_id: str,
        **kwargs
    ) -> Optional[Webhook]:
        webhook = await self.get_webhook(webhook_id)
        if not webhook:
            return None

        if "url" in kwargs:
            _validate_webhook_url(kwargs["url"])

        for key, value in kwargs.items():
            if value is not None and hasattr(webhook, key):
                setattr(webhook, key, value)

        webhook.updated_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def delete_webhook(self, webhook_id: str) -> bool:
        webhook = await self.get_webhook(webhook_id)
        if not webhook:
            return False

        await self.db.delete(webhook)
        await self.db.commit()
        return True

    async def trigger_event(
        self,
        event: str,
        payload: Dict[str, Any],
        project_id: Optional[str] = None
    ) -> List[WebhookDelivery]:
        webhooks = await self.get_webhooks_by_project(
            project_id=project_id,
            event=event,
            active_only=True
        )

        deliveries = []
        for webhook in webhooks:
            delivery = await self._send_webhook(webhook, event, payload)
            deliveries.append(delivery)

        return deliveries

    async def _send_webhook(
        self,
        webhook: Webhook,
        event: str,
        payload: Dict[str, Any]
    ) -> WebhookDelivery:
        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            event=event,
            payload=payload,
            retry_count=0,
            success=False
        )
        self.db.add(delivery)
        await self.db.flush()

        # SSRF 防御：发送前再次校验 URL，非法地址直接标记失败，不发起请求
        try:
            _validate_webhook_url(webhook.url)
        except ValueError as e:
            delivery.success = False
            delivery.error_message = str(e)
            delivery.response_status = None
            delivery.response_body = None
            delivery.duration_ms = 0
            webhook.last_triggered_at = datetime.now()
            webhook.last_status = "failed"
            webhook.failure_count += 1
            await self.db.commit()
            await self.db.refresh(delivery)
            return delivery

        signature = self._generate_signature(webhook.secret, payload)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
            "X-Webhook-ID": webhook.id,
            "X-Webhook-Signature": signature,
            "User-Agent": "TongWei-Webhook/1.0"
        }
        delivery.request_headers = headers

        start_time = datetime.now()
        success = False
        last_error = None
        response_status = None
        response_body = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                    response = await client.post(
                        webhook.url,
                        json=payload,
                        headers=headers
                    )
                    response_status = response.status_code
                    response_body = response.text

                    if response_status < 400:
                        success = True
                        break
                    else:
                        last_error = f"HTTP {response_status}"

            except Exception as e:
                last_error = str(e)

            if attempt < self.MAX_RETRIES - 1:
                delay = self.BASE_DELAY * (2 ** attempt)
                await asyncio.sleep(delay)
                delivery.retry_count += 1

        duration = int((datetime.now() - start_time).total_seconds() * 1000)

        delivery.success = success
        delivery.response_status = response_status
        delivery.response_body = response_body
        delivery.duration_ms = duration
        delivery.error_message = None if success else last_error

        webhook.last_triggered_at = datetime.now()
        webhook.last_status = "success" if success else "failed"
        if not success:
            webhook.failure_count += 1
        else:
            webhook.failure_count = 0

        await self.db.commit()
        await self.db.refresh(delivery)
        return delivery

    async def test_webhook(
        self,
        webhook: Webhook,
        event: str = WebhookEvent.TASK_CREATED,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if payload is None:
            payload = self._get_test_payload(event)

        # SSRF 防御：发送前校验 URL，非法地址直接返回失败结果，不发起请求
        try:
            _validate_webhook_url(webhook.url)
        except ValueError as e:
            return {
                "success": False,
                "status_code": None,
                "response_body": None,
                "duration_ms": 0,
                "error_message": str(e)
            }

        signature = self._generate_signature(webhook.secret, payload)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
            "X-Webhook-ID": webhook.id,
            "X-Webhook-Signature": signature,
            "User-Agent": "TongWei-Webhook/1.0"
        }

        start_time = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                response = await client.post(
                    webhook.url,
                    json=payload,
                    headers=headers
                )
                duration = int((datetime.now() - start_time).total_seconds() * 1000)
                return {
                    "success": response.status_code < 400,
                    "status_code": response.status_code,
                    "response_body": response.text[:1000],
                    "duration_ms": duration,
                    "error_message": None
                }
        except Exception as e:
            duration = int((datetime.now() - start_time).total_seconds() * 1000)
            return {
                "success": False,
                "status_code": None,
                "response_body": None,
                "duration_ms": duration,
                "error_message": str(e)
            }

    async def get_deliveries(
        self,
        webhook_id: Optional[str] = None,
        event: Optional[str] = None,
        success: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[List[WebhookDelivery], int]:
        conditions = []
        if webhook_id:
            conditions.append(WebhookDelivery.webhook_id == webhook_id)
        if event:
            conditions.append(WebhookDelivery.event == event)
        if success is not None:
            conditions.append(WebhookDelivery.success == success)

        query = select(WebhookDelivery)
        if conditions:
            query = query.where(and_(*conditions))

        count_query = select(func.count()).select_from(WebhookDelivery)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        query = query.order_by(WebhookDelivery.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        deliveries = result.scalars().all()

        return list(deliveries), total

    def _generate_signature(self, secret: str, payload: Dict[str, Any]) -> str:
        payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        signature = hmac.new(
            secret.encode("utf-8"),
            payload_str.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    def _generate_secret(self) -> str:
        return hmac.new(
            datetime.now().isoformat().encode(),
            b"webhook-secret",
            hashlib.sha256
        ).hexdigest()[:32]

    def _get_test_payload(self, event: str) -> Dict[str, Any]:
        payloads = {
            WebhookEvent.TASK_CREATED: {
                "event": "task.created",
                "data": {
                    "id": "test-task-id",
                    "name": "测试任务",
                    "status": "todo",
                    "project_id": "test-project-id"
                },
                "timestamp": datetime.now().isoformat()
            },
            WebhookEvent.TASK_UPDATED: {
                "event": "task.updated",
                "data": {
                    "id": "test-task-id",
                    "name": "测试任务",
                    "status": "in_progress",
                    "project_id": "test-project-id"
                },
                "timestamp": datetime.now().isoformat()
            },
            WebhookEvent.PROJECT_CREATED: {
                "event": "project.created",
                "data": {
                    "id": "test-project-id",
                    "name": "测试项目",
                    "status": "planning"
                },
                "timestamp": datetime.now().isoformat()
            },
            WebhookEvent.COMMENT_CREATED: {
                "event": "comment.created",
                "data": {
                    "id": "test-comment-id",
                    "content": "测试评论",
                    "task_id": "test-task-id"
                },
                "timestamp": datetime.now().isoformat()
            },
            WebhookEvent.RISK_CREATED: {
                "event": "risk.created",
                "data": {
                    "id": "test-risk-id",
                    "name": "测试风险",
                    "category": "technical",
                    "project_id": "test-project-id"
                },
                "timestamp": datetime.now().isoformat()
            }
        }
        return payloads.get(event, payloads[WebhookEvent.TASK_CREATED])


async def trigger_webhook_event(
    db: AsyncSession,
    event: str,
    payload: Dict[str, Any],
    project_id: Optional[str] = None
) -> None:
    service = WebhookService(db)
    await service.trigger_event(event, payload, project_id)

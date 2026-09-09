"""
PMI中国AI项目管理社区 - Zapier/Make集成服务
支持Zapier REST Hook规范，提供触发器和动作支持
"""

import hmac
import hashlib
import json
import asyncio
import secrets
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.config import settings


class ZapierEventType(str, Enum):
    """Zapier支持的事件类型"""
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_COMPLETED = "task.completed"
    PROJECT_CREATED = "project.created"
    COMMENT_ADDED = "comment.added"
    SPRINT_STARTED = "sprint.started"


# 触发器元数据定义
ZAPIER_TRIGGERS = [
    {
        "id": "task.created",
        "name": "任务创建",
        "description": "当新任务被创建时触发",
        "event_type": ZapierEventType.TASK_CREATED,
        "sample_data": "task_sample",
    },
    {
        "id": "task.updated",
        "name": "任务更新",
        "description": "当任务被更新时触发",
        "event_type": ZapierEventType.TASK_UPDATED,
        "sample_data": "task_sample",
    },
    {
        "id": "task.completed",
        "name": "任务完成",
        "description": "当任务状态变为已完成时触发",
        "event_type": ZapierEventType.TASK_COMPLETED,
        "sample_data": "task_completed_sample",
    },
    {
        "id": "project.created",
        "name": "项目创建",
        "description": "当新项目被创建时触发",
        "event_type": ZapierEventType.PROJECT_CREATED,
        "sample_data": "project_sample",
    },
    {
        "id": "comment.added",
        "name": "评论添加",
        "description": "当任务或项目添加新评论时触发",
        "event_type": ZapierEventType.COMMENT_ADDED,
        "sample_data": "comment_sample",
    },
    {
        "id": "sprint.started",
        "name": "Sprint开始",
        "description": "当Sprint开始时触发",
        "event_type": ZapierEventType.SPRINT_STARTED,
        "sample_data": "sprint_sample",
    },
]


# 示例数据模板
SAMPLE_DATA_TEMPLATES = {
    "task_sample": {
        "id": "task-550e8400-e29b-41d4-a716-446655440000",
        "name": "实现用户登录功能",
        "description": "开发基于JWT的用户认证系统，支持多因素认证",
        "status": "in_progress",
        "priority": 2,
        "project_id": "proj-550e8400-e29b-41d4-a716-446655440000",
        "project_name": "AI项目管理系统",
        "assignee_id": "user-550e8400-e29b-41d4-a716-446655440000",
        "assignee_name": "张三",
        "assignee_email": "zhangsan@example.com",
        "wbs_code": "1.2.3",
        "level": 2,
        "estimated_hours": 16.0,
        "actual_hours": 8.5,
        "progress": 53.0,
        "planned_start": "2024-05-20T09:00:00+08:00",
        "planned_end": "2024-05-24T18:00:00+08:00",
        "actual_start": "2024-05-20T09:30:00+08:00",
        "labels": ["frontend", "auth", "high-priority"],
        "category": "development",
        "is_milestone": False,
        "created_at": "2024-05-20T09:00:00+08:00",
        "updated_at": "2024-05-21T14:30:00+08:00",
        "url": "https://app.example.com/tasks/task-550e8400-e29b-41d4-a716-446655440000",
    },
    "task_completed_sample": {
        "id": "task-550e8400-e29b-41d4-a716-446655440000",
        "name": "实现用户登录功能",
        "description": "开发基于JWT的用户认证系统，支持多因素认证",
        "status": "done",
        "priority": 2,
        "project_id": "proj-550e8400-e29b-41d4-a716-446655440000",
        "project_name": "AI项目管理系统",
        "assignee_id": "user-550e8400-e29b-41d4-a716-446655440000",
        "assignee_name": "张三",
        "assignee_email": "zhangsan@example.com",
        "wbs_code": "1.2.3",
        "level": 2,
        "estimated_hours": 16.0,
        "actual_hours": 15.0,
        "progress": 100.0,
        "planned_start": "2024-05-20T09:00:00+08:00",
        "planned_end": "2024-05-24T18:00:00+08:00",
        "actual_start": "2024-05-20T09:30:00+08:00",
        "actual_end": "2024-05-23T17:00:00+08:00",
        "labels": ["frontend", "auth", "high-priority"],
        "category": "development",
        "is_milestone": False,
        "completed_by": "user-550e8400-e29b-41d4-a716-446655440000",
        "completed_by_name": "张三",
        "completed_at": "2024-05-23T17:00:00+08:00",
        "created_at": "2024-05-20T09:00:00+08:00",
        "updated_at": "2024-05-23T17:00:00+08:00",
        "url": "https://app.example.com/tasks/task-550e8400-e29b-41d4-a716-446655440000",
    },
    "project_sample": {
        "id": "proj-550e8400-e29b-41d4-a716-446655440000",
        "name": "AI项目管理系统",
        "description": "基于AI技术的智能项目管理系统，支持多维度项目管理",
        "status": "active",
        "priority": 1,
        "color": "#1890ff",
        "industry_type": "it_software",
        "project_type": "agile",
        "owner_id": "user-550e8400-e29b-41d4-a716-446655440000",
        "owner_name": "李四",
        "owner_email": "lisi@example.com",
        "start_date": "2024-05-01",
        "end_date": "2024-08-31",
        "budget": 500000.00,
        "baseline_budget": 480000.00,
        "actual_cost": 125000.00,
        "progress": 25.0,
        "task_count": 48,
        "completed_task_count": 12,
        "team_size": 8,
        "created_at": "2024-05-01T09:00:00+08:00",
        "updated_at": "2024-05-21T10:00:00+08:00",
        "url": "https://app.example.com/projects/proj-550e8400-e29b-41d4-a716-446655440000",
    },
    "comment_sample": {
        "id": "comment-550e8400-e29b-41d4-a716-446655440000",
        "content": "这个任务的设计文档已经更新，请大家查看最新版本。",
        "task_id": "task-550e8400-e29b-41d4-a716-446655440000",
        "task_name": "实现用户登录功能",
        "project_id": "proj-550e8400-e29b-41d4-a716-446655440000",
        "project_name": "AI项目管理系统",
        "user_id": "user-550e8400-e29b-41d4-a716-446655440000",
        "user_name": "王五",
        "user_email": "wangwu@example.com",
        "mentions": ["user-660e8400-e29b-41d4-a716-446655440001"],
        "parent_id": None,
        "created_at": "2024-05-21T15:30:00+08:00",
        "updated_at": "2024-05-21T15:30:00+08:00",
        "url": "https://app.example.com/tasks/task-550e8400-e29b-41d4-a716-446655440000#comment-550e8400-e29b-41d4-a716-446655440000",
    },
    "sprint_sample": {
        "id": "sprint-550e8400-e29b-41d4-a716-446655440000",
        "name": "Sprint 12 - AI功能迭代",
        "goal": "完成AI助手核心功能和NLP查询模块",
        "status": "active",
        "project_id": "proj-550e8400-e29b-41d4-a716-446655440000",
        "project_name": "AI项目管理系统",
        "start_date": "2024-05-20",
        "end_date": "2024-06-02",
        "total_story_points": 45,
        "completed_story_points": 0,
        "task_count": 12,
        "team_members": [
            {"id": "user-550e8400-e29b-41d4-a716-446655440000", "name": "张三"},
            {"id": "user-660e8400-e29b-41d4-a716-446655440001", "name": "李四"},
        ],
        "started_at": "2024-05-20T09:00:00+08:00",
        "started_by": "user-660e8400-e29b-41d4-a716-446655440001",
        "started_by_name": "李四",
        "created_at": "2024-05-15T14:00:00+08:00",
        "updated_at": "2024-05-20T09:00:00+08:00",
        "url": "https://app.example.com/sprints/sprint-550e8400-e29b-41d4-a716-446655440000",
    },
}


class ZapierService:
    """Zapier集成服务"""

    WEBHOOK_TIMEOUT = 30
    MAX_RETRIES = 3
    BASE_DELAY = 1

    def __init__(self):
        self._active_hooks: Dict[str, List[str]] = {}

    @staticmethod
    def generate_trigger_payload(event_type: ZapierEventType, data: Dict[str, Any]) -> Dict[str, Any]:
        """生成Zapier触发器payload"""
        return {
            "event": event_type.value,
            "data": data,
            "timestamp": datetime.now().isoformat() + "Z",
            "source": "tongwei-pms",
            "version": settings.VERSION,
        }

    @staticmethod
    def validate_webhook_signature(signature: str, body: bytes, secret: str) -> bool:
        """验证Zapier webhook签名"""
        if not signature or not secret:
            return False

        expected = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()

        # 支持 "sha256=xxx" 或纯 hex 格式
        if signature.startswith("sha256="):
            signature = signature[7:]

        return hmac.compare_digest(expected, signature)

    @staticmethod
    def generate_webhook_secret() -> str:
        """生成webhook密钥"""
        return secrets.token_urlsafe(32)

    def get_available_triggers(self) -> List[Dict[str, Any]]:
        """获取可用的触发器列表"""
        return [
            {
                "id": trigger["id"],
                "name": trigger["name"],
                "description": trigger["description"],
                "event_type": trigger["event_type"].value,
            }
            for trigger in ZAPIER_TRIGGERS
        ]

    def get_sample_data(self, trigger_id: Optional[str] = None) -> Dict[str, Any]:
        """获取示例数据（Zapier测试用）"""
        if trigger_id:
            trigger = next((t for t in ZAPIER_TRIGGERS if t["id"] == trigger_id), None)
            if trigger:
                sample_key = trigger["sample_data"]
                return {
                    "trigger_id": trigger_id,
                    "trigger_name": trigger["name"],
                    "sample": SAMPLE_DATA_TEMPLATES.get(sample_key, {}),
                }
            return {"error": f"未知的触发器: {trigger_id}"}

        # 返回所有触发器的示例数据
        return {
            trigger["id"]: {
                "trigger_name": trigger["name"],
                "sample": SAMPLE_DATA_TEMPLATES.get(trigger["sample_data"], {}),
            }
            for trigger in ZAPIER_TRIGGERS
        }

    def get_trigger_sample_data(self, event_type: ZapierEventType) -> Dict[str, Any]:
        """根据事件类型获取示例数据"""
        trigger = next(
            (t for t in ZAPIER_TRIGGERS if t["event_type"] == event_type),
            None
        )
        if trigger:
            return SAMPLE_DATA_TEMPLATES.get(trigger["sample_data"], {})
        return {}

    async def send_webhook(
        self,
        hook_url: str,
        payload: Dict[str, Any],
        secret: Optional[str] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """发送webhook到Zapier"""
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-Zapier-Event": payload.get("event", ""),
            "X-Zapier-Source": "tongwei-pms",
            "User-Agent": "TongWei-PMS-Webhook/1.0",
        }

        if secret:
            signature = hmac.new(
                secret.encode("utf-8"),
                body,
                hashlib.sha256
            ).hexdigest()
            headers["X-Zapier-Signature"] = f"sha256={signature}"

        try:
            async with httpx.AsyncClient(timeout=self.WEBHOOK_TIMEOUT) as client:
                response = await client.post(
                    hook_url,
                    content=body,
                    headers=headers
                )

                success = response.status_code < 400
                result = {
                    "success": success,
                    "status_code": response.status_code,
                    "response_body": response.text[:1000],
                    "hook_url": hook_url,
                }

                if not success and retry_count < self.MAX_RETRIES:
                    delay = self.BASE_DELAY * (2 ** retry_count)
                    await asyncio.sleep(delay)
                    return await self.send_webhook(
                        hook_url, payload, secret, retry_count + 1
                    )

                return result

        except Exception as e:
            if retry_count < self.MAX_RETRIES:
                delay = self.BASE_DELAY * (2 ** retry_count)
                await asyncio.sleep(delay)
                return await self.send_webhook(
                    hook_url, payload, secret, retry_count + 1
                )

            return {
                "success": False,
                "error": str(e),
                "hook_url": hook_url,
            }

    async def broadcast_event(
        self,
        event_type: ZapierEventType,
        data: Dict[str, Any],
        hook_urls: List[str],
        secret: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """广播事件到多个Zapier hook URL"""
        payload = self.generate_trigger_payload(event_type, data)

        tasks = [
            self.send_webhook(url, payload, secret)
            for url in hook_urls
        ]

        return await asyncio.gather(*tasks, return_exceptions=True)


class ZapierWebhookStore:
    """Zapier webhook订阅存储（基于数据库，持久化，重启不丢失）"""

    async def subscribe(
        self,
        trigger_id: str,
        hook_url: str,
        user_id: str,
        secret: Optional[str] = None,
    ) -> str:
        from app.db.session import async_session_maker
        from app.models.zapier import ZapierSubscription

        sub_id = secrets.token_urlsafe(16)
        async with async_session_maker() as db:
            sub = ZapierSubscription(
                id=sub_id,
                user_id=user_id,
                trigger_id=trigger_id,
                hook_url=hook_url,
                secret=secret or ZapierService.generate_webhook_secret(),
                is_active=True,
            )
            db.add(sub)
            await db.commit()
        return sub_id

    async def unsubscribe(self, sub_id: str) -> bool:
        from app.db.session import async_session_maker
        from app.models.zapier import ZapierSubscription

        async with async_session_maker() as db:
            sub = (await db.execute(
                select(ZapierSubscription).where(ZapierSubscription.id == sub_id)
            )).scalar_one_or_none()
            if not sub:
                return False
            sub.is_active = False
            await db.commit()
        return True

    async def get_subscription(self, sub_id: str) -> Optional[Dict[str, Any]]:
        from app.db.session import async_session_maker
        from app.models.zapier import ZapierSubscription

        async with async_session_maker() as db:
            sub = (await db.execute(
                select(ZapierSubscription).where(ZapierSubscription.id == sub_id)
            )).scalar_one_or_none()
            if not sub:
                return None
            return self._to_dict(sub)

    async def get_active_hooks(self, trigger_id: str) -> List[Dict[str, Any]]:
        from app.db.session import async_session_maker
        from app.models.zapier import ZapierSubscription

        async with async_session_maker() as db:
            rows = (await db.execute(
                select(ZapierSubscription).where(
                    ZapierSubscription.trigger_id == trigger_id,
                    ZapierSubscription.is_active == True,
                )
            )).scalars().all()
            return [self._to_dict(r) for r in rows]

    async def get_all_active_hooks(self) -> List[Dict[str, Any]]:
        from app.db.session import async_session_maker
        from app.models.zapier import ZapierSubscription

        async with async_session_maker() as db:
            rows = (await db.execute(
                select(ZapierSubscription).where(ZapierSubscription.is_active == True)
            )).scalars().all()
            return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(sub) -> Dict[str, Any]:
        return {
            "id": sub.id,
            "trigger_id": sub.trigger_id,
            "hook_url": sub.hook_url,
            "user_id": sub.user_id,
            "secret": sub.secret,
            "is_active": sub.is_active,
            "created_at": sub.created_at.isoformat() if sub.created_at else None,
        }


# 全局实例
zapier_service = ZapierService()
zapier_webhook_store = ZapierWebhookStore()


async def notify_zapier_event(
    event_type: ZapierEventType,
    data: Dict[str, Any],
    trigger_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """通知Zapier事件（便捷函数，从数据库读取订阅）"""
    tid = trigger_id or event_type.value
    hooks = await zapier_webhook_store.get_active_hooks(tid)

    if not hooks:
        return []

    hook_urls = [h["hook_url"] for h in hooks]
    secrets_list = [h.get("secret") for h in hooks]

    # 使用第一个secret（通常所有hooks共享一个secret）
    common_secret = secrets_list[0] if secrets_list else None

    return await zapier_service.broadcast_event(
        event_type, data, hook_urls, common_secret
    )

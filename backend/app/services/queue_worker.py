"""
PMI中国AI项目管理社区 - 后台任务处理器
基于消息队列的异步任务处理
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.messaging import message_queue, QUEUE_STREAMS

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """后台任务处理器基类"""

    def __init__(self, queue_name: str, worker_name: str, group_name: str = "default"):
        self.queue_name = queue_name
        self.worker_name = worker_name
        self.group_name = group_name
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """启动 Worker"""
        if self._running:
            logger.warning(f"Worker {self.worker_name} 已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"Worker 启动: {self.worker_name} -> {self.queue_name}")

    async def stop(self):
        """停止 Worker"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info(f"Worker 停止: {self.worker_name}")

    async def _run(self):
        """运行消费者循环"""
        try:
            await message_queue.subscribe(
                stream=self.queue_name,
                group=self.group_name,
                consumer=self.worker_name,
                callback=self._handle_message,
            )
        except asyncio.CancelledError:
            logger.info(f"Worker 任务取消: {self.worker_name}")
        except Exception as e:
            logger.error(f"Worker 异常: {self.worker_name} - {e}", exc_info=True)

    async def _handle_message(self, message: Dict[str, Any]) -> bool:
        """消息处理入口。

        返回 True=成功(确认)，False=失败。失败(或抛异常)时由消费层
        app.core.messaging 统一执行指数退避重投；超过 BACKOFF_MAX_RETRIES 后转入死信。
        退避重投由消息队列层以独立 asyncio 任务调度(asyncio.sleep 期间不持有任何
        DB/Redis 连接)，各 Worker 的 process() 也在 async with 会话上下文内自行
        打开/关闭 DB 连接，因此重试间隔绝不长期占用连接。
        """
        msg_id = message.get("_id", "unknown")
        logger.info(f"📥 {self.worker_name} 收到消息: {msg_id}")

        try:
            result = await self.process(message)
            if result:
                logger.info(f"✅ {self.worker_name} 处理成功: {msg_id}")
            else:
                logger.warning(f"⚠️ {self.worker_name} 处理返回失败: {msg_id}")
            return result
        except Exception as e:
            logger.error(f"❌ {self.worker_name} 处理异常 {msg_id}: {e}", exc_info=True)
            return False

    @abstractmethod
    async def process(self, message: Dict[str, Any]) -> bool:
        """
        处理消息的具体逻辑

        Args:
            message: 消息内容

        Returns:
            bool: 处理是否成功
        """
        pass


class EmailWorker(BaseWorker):
    """邮件发送 Worker"""

    def __init__(self, worker_name: str = "email_worker"):
        super().__init__("email_queue", worker_name, "email_group")

    async def process(self, message: Dict[str, Any]) -> bool:
        """处理邮件发送任务（真实调用 SMTP）"""
        to = message.get("to")
        subject = message.get("subject")
        body = message.get("body")
        html = message.get("html")
        template = message.get("template")
        context = message.get("context", {})

        if not to or not subject:
            logger.error("邮件任务缺少必要字段: to 或 subject")
            return True  # 返回 True 避免重复处理无效消息

        if isinstance(to, str):
            to = [to]

        from app.core import email as email_module

        try:
            # 使用真实 SMTP 发送；未配置 SMTP 时 send_email 会抛出明确异常
            await email_module.send_email(to=to, subject=subject, body=body or "", html=html)
            if template:
                logger.info(f"使用模板: {template}, 上下文: {context}")
            return True
        except email_module.EmailNotConfiguredException as e:
            # 未配置 SMTP 属于不可重试的环境问题，直接确认丢弃，避免无限重试
            logger.warning(f"邮件未发送（SMTP 未配置）: {to} - {e}")
            return True
        except Exception as e:
            logger.error(f"邮件发送失败: {e}", exc_info=True)
            return False  # 返回 False 以便消息队列重试


class NotificationWorker(BaseWorker):
    """通知推送 Worker"""

    def __init__(self, worker_name: str = "notification_worker"):
        super().__init__("notification_queue", worker_name, "notification_group")

    async def process(self, message: Dict[str, Any]) -> bool:
        """处理通知推送任务（真实持久化到通知表）"""
        user_id = message.get("user_id")
        notification_type = message.get("type", "system")
        title = message.get("title")
        content = message.get("content")
        related_type = message.get("related_type")
        related_id = message.get("related_id")

        if not user_id or not title:
            logger.error("通知任务缺少必要字段: user_id 或 title")
            return True

        from app.db.session import async_session_maker
        from app.services.notification_service import create_notification

        try:
            async with async_session_maker() as db:
                await create_notification(
                    db=db,
                    user_id=user_id,
                    type=notification_type,
                    title=title,
                    content=content,
                    related_type=related_type,
                    related_id=related_id,
                )
            logger.info(f"🔔 站内通知已持久化: {title} -> {user_id}")
            return True
        except Exception as e:
            logger.error(f"通知持久化失败: {e}", exc_info=True)
            return False


class ReportWorker(BaseWorker):
    """报表生成 Worker"""

    def __init__(self, worker_name: str = "report_worker"):
        super().__init__("report_queue", worker_name, "report_group")

    async def process(self, message: Dict[str, Any]) -> bool:
        """处理报表生成任务（真实调用 ReportService 生成报表）"""
        report_type = message.get("report_type")
        project_id = message.get("project_id")
        params = message.get("params", {}) or {}
        output_format = message.get("format", "csv")
        callback_url = message.get("callback_url")

        if not report_type or not project_id:
            logger.error("报表任务缺少必要字段: report_type 或 project_id")
            return True

        from datetime import date as _date, datetime as _dt

        def _parse_date(v):
            if v is None:
                return None
            if isinstance(v, _date):
                return v
            try:
                return _dt.strptime(str(v), "%Y-%m-%d").date()
            except Exception:
                return None

        from app.db.session import async_session_maker
        from app.services.report_service import ReportService

        try:
            async with async_session_maker() as db:
                service = ReportService(db)
                content, mime = await service.export_report(
                    project_id=project_id,
                    report_type=report_type,
                    format_type=output_format,
                    start_date=_parse_date(params.get("start_date")),
                    end_date=_parse_date(params.get("end_date")),
                )

            if not content:
                logger.warning(f"报表生成为空: {report_type} 项目={project_id}")
                return True

            logger.info(f"📊 报表生成完成: {report_type} 项目={project_id} 大小={len(content)}B")

            if callback_url:
                import httpx
                async with httpx.AsyncClient(timeout=30.0) as client:
                    await client.post(callback_url, content=content, headers={"Content-Type": mime})

            return True
        except Exception as e:
            logger.error(f"报表生成失败: {e}", exc_info=True)
            return False


class WebhookWorker(BaseWorker):
    """Webhook 推送 Worker"""

    def __init__(self, worker_name: str = "webhook_worker"):
        super().__init__("webhook_queue", worker_name, "webhook_group")

    async def process(self, message: Dict[str, Any]) -> bool:
        """处理 Webhook 推送任务（失败由基类统一指数退避重试并死信）"""
        url = message.get("url")
        event = message.get("event")
        payload = message.get("payload", {})
        headers = message.get("headers", {})

        if not url or not event:
            logger.error("Webhook 任务缺少必要字段: url 或 event")
            return True  # 无效消息，直接确认丢弃，不重试

        try:
            logger.info(f"🔗 推送 Webhook: {event} -> {url}")

            import httpx

            default_headers = {
                "Content-Type": "application/json",
                "X-Webhook-Event": event,
                "X-Webhook-Timestamp": datetime.now().isoformat(),
                **headers,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=default_headers,
                )

            if response.status_code < 400:
                logger.info(f"✅ Webhook 推送成功: {response.status_code}")
                return True
            logger.warning(f"⚠️ Webhook 推送失败: {response.status_code}")
            return False  # 交给基类指数退避重试，超上限进入死信
        except Exception as e:
            logger.error(f"Webhook 推送异常: {e}")
            return False  # 交给基类重试 + 死信


class WorkerManager:
    """Worker 管理器"""

    def __init__(self):
        self.workers: Dict[str, BaseWorker] = {}

    def register(self, worker: BaseWorker):
        """注册 Worker"""
        self.workers[worker.worker_name] = worker
        logger.info(f"Worker 已注册: {worker.worker_name}")

    async def start_all(self):
        """启动所有 Worker"""
        logger.info("启动所有 Worker...")
        for worker in self.workers.values():
            await worker.start()

    async def stop_all(self):
        """停止所有 Worker"""
        logger.info("停止所有 Worker...")
        for worker in self.workers.values():
            await worker.stop()

    def get_status(self) -> Dict[str, Any]:
        """获取所有 Worker 状态"""
        return {
            name: {
                "queue": worker.queue_name,
                "running": worker._running,
                "group": worker.group_name,
            }
            for name, worker in self.workers.items()
        }


# 全局 Worker 管理器
worker_manager = WorkerManager()

# 注册默认 Worker
worker_manager.register(EmailWorker())
worker_manager.register(NotificationWorker())
worker_manager.register(ReportWorker())
worker_manager.register(WebhookWorker())

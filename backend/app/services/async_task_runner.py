"""
异步任务执行引擎。
- TASK_HANDLERS 注册表：task_type -> async handler(db, task, params)
- dispatch_task 用 asyncio.create_task 后台执行，立即返回，不阻塞 HTTP 响应
- handler 通过 publish_progress 推送实时进度；完成/失败推送 task_done/task_failed 事件
"""
import asyncio
import logging
from typing import Dict, Callable
from sqlalchemy import select

from app.db.session import async_session_maker
from app.core.websocket import publish_event
from app.models.async_task import AsyncTask, AsyncTaskStatus

logger = logging.getLogger(__name__)

TASK_HANDLERS: Dict[str, Callable] = {}
_RUNNING: set = set()


def register_handler(task_type: str, fn: Callable):
    TASK_HANDLERS[task_type] = fn


async def publish_progress(task: AsyncTask, progress: int, message: str = "", db=None):
    task.progress = progress
    task.message = message
    if db is not None:
        await db.commit()
    await publish_event(task.user_id, {
        "type": "task_progress",
        "task_id": task.id,
        "task_type": task.task_type,
        "progress": progress,
        "message": message,
    })


async def _run_task(task_id: str):
    async with async_session_maker() as db:
        task = (await db.execute(select(AsyncTask).where(AsyncTask.id == task_id))).scalar_one_or_none()
        if not task:
            logger.warning("async task not found: %s", task_id)
            return
        handler = TASK_HANDLERS.get(task.task_type)
        if not handler:
            task.status = AsyncTaskStatus.FAILED.value
            task.error = f"未注册的任务类型: {task.task_type}"
            await db.commit()
            return
        task.status = AsyncTaskStatus.RUNNING.value
        await db.commit()
        try:
            result = await handler(db, task, task.params or {})
            task.status = AsyncTaskStatus.SUCCESS.value
            task.progress = 100
            task.message = "完成"
            task.result = result
            await db.commit()
            await publish_event(task.user_id, {
                "type": "task_done",
                "task_id": task.id,
                "task_type": task.task_type,
                "result": result,
            })
        except Exception as e:
            logger.exception("async task failed: %s", task_id)
            task.status = AsyncTaskStatus.FAILED.value
            task.error = str(e)
            await db.commit()
            await publish_event(task.user_id, {
                "type": "task_failed",
                "task_id": task.id,
                "task_type": task.task_type,
                "error": str(e),
            })
        finally:
            _RUNNING.discard(asyncio.current_task())


async def dispatch_task(task_id: str):
    """触发后台任务执行（不阻塞调用方）"""
    t = asyncio.create_task(_run_task(task_id))
    _RUNNING.add(t)
    return t

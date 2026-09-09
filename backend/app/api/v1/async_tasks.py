"""
异步任务管理 API。
前端创建异步任务后立即拿到 task_id，随后通过 /ws/events 实时接收进度与结果。
"""
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.security import get_current_user
from app.core.response import success, error_dict
from app.models import User
from app.models.async_task import AsyncTask, AsyncTaskStatus
from app.services.async_task_runner import dispatch_task, TASK_HANDLERS

router = APIRouter()


@router.post("/async-tasks")
async def create_async_task(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task_type = payload.get("task_type")
    if not task_type or task_type not in TASK_HANDLERS:
        return error_dict(code=400, message=f"未知或尚未注册的任务类型: {task_type}")
    params = payload.get("params", {}) or {}
    task = AsyncTask(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        task_type=task_type,
        params=params,
        status=AsyncTaskStatus.PENDING.value,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await dispatch_task(task.id)
    return success(data={"task_id": task.id, "status": task.status, "task_type": task.task_type})


@router.get("/async-tasks/{task_id}")
async def get_async_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = (await db.execute(select(AsyncTask).where(AsyncTask.id == task_id))).scalar_one_or_none()
    if not task:
        return error_dict(code=404, message="任务不存在")
    if task.user_id != current_user.id:
        return error_dict(code=403, message="无权访问该任务")
    return success(data=task.to_dict())


@router.get("/async-tasks")
async def list_my_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = 20,
):
    rows = (await db.execute(
        select(AsyncTask)
        .where(AsyncTask.user_id == current_user.id)
        .order_by(AsyncTask.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return success(data=[t.to_dict() for t in rows])

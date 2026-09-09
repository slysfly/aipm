"""
PMI中国AI项目管理社区 - 重复任务API路由

[PMBOK KA: 进度管理 (Schedule) — 重复任务、周期性工作包]
对应PMI第6版标准：重复任务管理
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import RecurringTask, RecurringTaskInstance, Task, User, Project
from app.schemas.recurring_task import (
    RecurringTaskCreate, RecurringTaskUpdate, RecurringTaskResponse,
    RecurringTaskListResponse, RecurringTaskInstanceListResponse,
    RecurringTaskToggleResponse, RecurringTaskRunNowResponse,
    RecurringTaskPreviewResponse, RecurringTaskInstanceResponse
)
from app.schemas import SuccessResponse
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user
from app.services.recurring_task_scheduler import RecurringTaskScheduler

router = APIRouter()


@router.post("/", response_model=RecurringTaskResponse, status_code=201)
async def create_recurring_task(
    task_in: RecurringTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 验证项目存在
    project_result = await db.execute(
        select(Project).where(Project.id == task_in.project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise NotFoundException(message="项目不存在")

    # 验证基础任务存在（如果提供了）
    if task_in.base_task_id:
        task_result = await db.execute(
            select(Task).where(Task.id == task_in.base_task_id, Task.is_deleted == False)
        )
        base_task = task_result.scalar_one_or_none()
        if not base_task:
            raise NotFoundException(message="基础任务不存在")

    # 计算下次执行时间
    now = datetime.now()
    kwargs = {}
    if task_in.pattern == "weekly":
        kwargs["week_days"] = task_in.week_days or [1]
    elif task_in.pattern == "monthly":
        kwargs["month_day"] = task_in.month_day or 1
    elif task_in.pattern == "custom":
        kwargs["interval_days"] = task_in.interval_days or 1

    next_run = RecurringTaskScheduler.calculate_next_run(
        task_in.pattern,
        now,
        **kwargs
    )

    recurring_task = RecurringTask(
        base_task_id=task_in.base_task_id,
        project_id=task_in.project_id,
        pattern=task_in.pattern,
        interval_days=task_in.interval_days,
        week_days=task_in.week_days,
        month_day=task_in.month_day,
        end_condition=task_in.end_condition,
        end_after_count=task_in.end_after_count,
        end_date=task_in.end_date,
        next_run_at=next_run,
        is_active=task_in.is_active,
        created_by=current_user.id,
    )

    try:
        db.add(recurring_task)
        await db.commit()
        await db.refresh(recurring_task)
    except Exception:
        # 单事务：父规则写入失败整体回滚，避免脏会话影响后续请求
        await db.rollback()
        raise

    return recurring_task


@router.get("/", response_model=RecurringTaskListResponse)
async def list_recurring_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    project_id: Optional[str] = None,
    pattern: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(RecurringTask)
    count_query = select(func.count(RecurringTask.id))

    if project_id:
        query = query.where(RecurringTask.project_id == project_id)
        count_query = count_query.where(RecurringTask.project_id == project_id)

    if pattern:
        query = query.where(RecurringTask.pattern == pattern)
        count_query = count_query.where(RecurringTask.pattern == pattern)

    if is_active is not None:
        query = query.where(RecurringTask.is_active == is_active)
        count_query = count_query.where(RecurringTask.is_active == is_active)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(RecurringTask.created_at.desc())

    result = await db.execute(query)
    tasks = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return RecurringTaskListResponse(
        items=[RecurringTaskResponse.model_validate(t) for t in tasks],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{task_id}", response_model=RecurringTaskResponse)
async def get_recurring_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(RecurringTask).where(RecurringTask.id == task_id))
    recurring_task = result.scalar_one_or_none()

    if not recurring_task:
        raise NotFoundException(message="重复任务不存在")

    return recurring_task


@router.put("/{task_id}", response_model=RecurringTaskResponse)
async def update_recurring_task(
    task_id: str,
    task_in: RecurringTaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(RecurringTask).where(RecurringTask.id == task_id))
    recurring_task = result.scalar_one_or_none()

    if not recurring_task:
        raise NotFoundException(message="重复任务不存在")

    update_data = task_in.model_dump(exclude_unset=True)

    # 如果更新了模式相关字段，重新计算下次执行时间
    pattern_changed = "pattern" in update_data
    interval_changed = "interval_days" in update_data
    week_days_changed = "week_days" in update_data
    month_day_changed = "month_day" in update_data

    for field, value in update_data.items():
        setattr(recurring_task, field, value)

    if pattern_changed or interval_changed or week_days_changed or month_day_changed:
        kwargs = {}
        if recurring_task.pattern == "weekly":
            kwargs["week_days"] = recurring_task.week_days or [1]
        elif recurring_task.pattern == "monthly":
            kwargs["month_day"] = recurring_task.month_day or 1
        elif recurring_task.pattern == "custom":
            kwargs["interval_days"] = recurring_task.interval_days or 1

        now = datetime.now()
        recurring_task.next_run_at = RecurringTaskScheduler.calculate_next_run(
            recurring_task.pattern,
            now,
            **kwargs
        )

    recurring_task.updated_at = datetime.now()

    await db.commit()
    await db.refresh(recurring_task)

    return recurring_task


@router.delete("/{task_id}", response_model=SuccessResponse)
async def delete_recurring_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(RecurringTask).where(RecurringTask.id == task_id))
    recurring_task = result.scalar_one_or_none()

    if not recurring_task:
        raise NotFoundException(message="重复任务不存在")

    await db.delete(recurring_task)
    await db.commit()

    return SuccessResponse(message="重复任务删除成功")


@router.post("/{task_id}/toggle", response_model=RecurringTaskToggleResponse)
async def toggle_recurring_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(RecurringTask).where(RecurringTask.id == task_id))
    recurring_task = result.scalar_one_or_none()

    if not recurring_task:
        raise NotFoundException(message="重复任务不存在")

    recurring_task.is_active = not recurring_task.is_active

    # 如果启用，重新计算下次执行时间
    if recurring_task.is_active:
        kwargs = {}
        if recurring_task.pattern == "weekly":
            kwargs["week_days"] = recurring_task.week_days or [1]
        elif recurring_task.pattern == "monthly":
            kwargs["month_day"] = recurring_task.month_day or 1
        elif recurring_task.pattern == "custom":
            kwargs["interval_days"] = recurring_task.interval_days or 1

        now = datetime.now()
        recurring_task.next_run_at = RecurringTaskScheduler.calculate_next_run(
            recurring_task.pattern,
            now,
            **kwargs
        )

    recurring_task.updated_at = datetime.now()
    await db.commit()

    status_text = "启用" if recurring_task.is_active else "停用"
    return RecurringTaskToggleResponse(
        id=recurring_task.id,
        is_active=recurring_task.is_active,
        message=f"重复任务已{status_text}"
    )


@router.post("/{task_id}/run-now", response_model=RecurringTaskRunNowResponse)
async def run_recurring_task_now(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = await RecurringTaskScheduler.run_now(db, task_id)

    return RecurringTaskRunNowResponse(
        id=task_id,
        task_id=task.id,
        message="重复任务已立即执行"
    )


@router.get("/{task_id}/instances", response_model=RecurringTaskInstanceListResponse)
async def get_recurring_task_instances(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(RecurringTask).where(RecurringTask.id == task_id))
    recurring_task = result.scalar_one_or_none()

    if not recurring_task:
        raise NotFoundException(message="重复任务不存在")

    query = select(RecurringTaskInstance).where(RecurringTaskInstance.recurring_task_id == task_id)
    count_query = select(func.count(RecurringTaskInstance.id)).where(
        RecurringTaskInstance.recurring_task_id == task_id
    )

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(RecurringTaskInstance.sequence_number.desc())

    result = await db.execute(query)
    instances = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return RecurringTaskInstanceListResponse(
        items=[RecurringTaskInstanceResponse.model_validate(i) for i in instances],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.post("/preview", response_model=RecurringTaskPreviewResponse)
async def preview_recurring_task(
    pattern: str,
    start_date: Optional[datetime] = None,
    interval_days: int = Query(1, ge=1),
    week_days: Optional[str] = Query(None),
    month_day: int = Query(1, ge=1, le=31),
    count: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if pattern not in ["daily", "weekly", "biweekly", "monthly", "quarterly", "yearly", "custom"]:
        raise ValidationException(message="无效的重复模式")

    start = start_date or datetime.now()

    kwargs = {}
    if pattern == "weekly":
        if week_days:
            try:
                kwargs["week_days"] = [int(d) for d in week_days.split(",")]
            except ValueError:
                kwargs["week_days"] = [1]
        else:
            kwargs["week_days"] = [1]
    elif pattern == "monthly":
        kwargs["month_day"] = month_day
    elif pattern == "custom":
        kwargs["interval_days"] = interval_days

    preview_dates = RecurringTaskScheduler.preview_next_runs(
        pattern, start, count, **kwargs
    )

    next_run = preview_dates[0] if preview_dates else None

    return RecurringTaskPreviewResponse(
        next_run_at=next_run,
        preview_dates=preview_dates
    )

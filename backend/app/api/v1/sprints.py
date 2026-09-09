"""
[PMBOK KA: 范围管理/进度管理 | PG: 规划 (Scope/Schedule/Planning) — Sprint规划、燃尽图、迭代跟踪]
对应PMI第6版标准：Sprint规划、迭代管理、燃尽图跟踪

PMBOK 7th Principle: Tailoring/Delivery | Domain: Development Approach — 敏捷裁剪、迭代交付
PMBOK 8th: Hybrid Agile-AI Methodology"""

import json
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case, desc
from typing import List, Optional
from datetime import datetime, date, timedelta

from app.db.session import get_db
from app.models import Sprint, SprintTask, Task, User, Project
from app.schemas.sprint import (
    SprintCreate, SprintUpdate, SprintResponse, SprintListResponse,
    SprintTaskCreate, SprintTaskResponse, SprintReportResponse, SprintBurndownPoint,
    SprintBurnupPoint, SuccessResponse
)
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=SprintResponse, status_code=201)
async def create_sprint(
    sprint_in: SprintCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project_result = await db.execute(
        select(Project).where(Project.id == sprint_in.project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise NotFoundException(message="项目不存在")

    sprint = Sprint(
        name=sprint_in.name,
        goal=sprint_in.goal,
        start_date=sprint_in.start_date,
        end_date=sprint_in.end_date,
        status=sprint_in.status,
        project_id=sprint_in.project_id,
        velocity=sprint_in.velocity,
        capacity=sprint_in.capacity,
        acceptance_plan=sprint_in.acceptance_plan,
        created_by=current_user.id,
    )

    db.add(sprint)
    await db.commit()
    await db.refresh(sprint)

    # 级联完成：新增 Sprint 可能影响项目完成态（如原已全部完成则本项目应回退）
    try:
        from app.services.completion_service import recompute_project_completion
        await recompute_project_completion(db, sprint.project_id)
        await db.commit()
    except Exception as e:
        logger.warning("级联完成计算失败（已忽略）: %s", e, exc_info=True)

    return sprint


@router.get("/", response_model=SprintListResponse)
async def list_sprints(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Sprint)
    count_query = select(func.count(Sprint.id))

    if project_id:
        query = query.where(Sprint.project_id == project_id)
        count_query = count_query.where(Sprint.project_id == project_id)

    if status:
        query = query.where(Sprint.status == status)
        count_query = count_query.where(Sprint.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Sprint.created_at.desc())

    result = await db.execute(query)
    sprints = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return SprintListResponse(
        items=[SprintResponse.model_validate(s) for s in sprints],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{sprint_id}", response_model=SprintResponse)
async def get_sprint(
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = result.scalar_one_or_none()

    if not sprint:
        raise NotFoundException(message="Sprint不存在")

    return sprint


@router.put("/{sprint_id}", response_model=SprintResponse)
async def update_sprint(
    sprint_id: str,
    sprint_in: SprintUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = result.scalar_one_or_none()

    if not sprint:
        raise NotFoundException(message="Sprint不存在")

    update_data = sprint_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(sprint, field, value)

    sprint.updated_at = datetime.now()

    await db.commit()
    await db.refresh(sprint)

    # 级联完成：Sprint 状态变化可能影响项目完成态
    try:
        from app.services.completion_service import recompute_project_completion
        await recompute_project_completion(db, sprint.project_id)
        await db.commit()
    except Exception as e:
        logger.warning("级联完成计算失败（已忽略）: %s", e, exc_info=True)

    return sprint


@router.delete("/{sprint_id}", response_model=SuccessResponse)
async def delete_sprint(
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = result.scalar_one_or_none()

    if not sprint:
        raise NotFoundException(message="Sprint不存在")

    project_id = sprint.project_id
    await db.delete(sprint)
    await db.commit()

    # 级联完成：Sprint 移除后重算项目完成态
    try:
        from app.services.completion_service import recompute_project_completion
        await recompute_project_completion(db, project_id)
        await db.commit()
    except Exception as e:
        logger.warning("级联完成计算失败（已忽略）: %s", e, exc_info=True)

    return SuccessResponse(message="Sprint删除成功")


@router.post("/{sprint_id}/start", response_model=SprintResponse)
async def start_sprint(
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = result.scalar_one_or_none()

    if not sprint:
        raise NotFoundException(message="Sprint不存在")

    if sprint.status != "planning":
        raise ValidationException(message="只能开始处于规划状态的Sprint")

    sprint.status = "active"
    if not sprint.start_date:
        sprint.start_date = date.today()
    if not sprint.end_date:
        sprint.end_date = date.today() + timedelta(days=14)
    sprint.updated_at = datetime.now()

    await db.commit()
    await db.refresh(sprint)

    try:
        from app.services.completion_service import recompute_project_completion
        await recompute_project_completion(db, sprint.project_id)
        await db.commit()
    except Exception as e:
        logger.warning("级联完成计算失败（已忽略）: %s", e, exc_info=True)

    return sprint


@router.post("/{sprint_id}/complete", response_model=SprintResponse)
async def complete_sprint(
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = result.scalar_one_or_none()

    if not sprint:
        raise NotFoundException(message="Sprint不存在")

    if sprint.status != "active":
        raise ValidationException(message="只能完成进行中的Sprint")

    sprint.status = "completed"
    sprint.updated_at = datetime.now()

    await db.commit()
    await db.refresh(sprint)

    try:
        from app.services.completion_service import recompute_project_completion
        await recompute_project_completion(db, sprint.project_id)
        await db.commit()
    except Exception as e:
        logger.warning("级联完成计算失败（已忽略）: %s", e, exc_info=True)

    return sprint


# ---------------------------------------------------------------------------
# 任务关联 CRUD
# ---------------------------------------------------------------------------

@router.post("/{sprint_id}/tasks", response_model=SprintTaskResponse)
async def add_task_to_sprint(
    sprint_id: str,
    task_in: SprintTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sprint_result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = sprint_result.scalar_one_or_none()
    if not sprint:
        raise NotFoundException(message="Sprint不存在")

    task_result = await db.execute(select(Task).where(Task.id == task_in.task_id, Task.is_deleted == False))
    task = task_result.scalar_one_or_none()
    if not task:
        raise NotFoundException(message="任务不存在")

    existing_result = await db.execute(
        select(SprintTask).where(SprintTask.sprint_id == sprint_id, SprintTask.task_id == task_in.task_id)
    )
    if existing_result.scalar_one_or_none():
        raise ValidationException(message="任务已在此Sprint中")

    sprint_task = SprintTask(
        sprint_id=sprint_id,
        task_id=task_in.task_id,
        status="active"
    )

    db.add(sprint_task)
    await db.commit()
    await db.refresh(sprint_task)

    return sprint_task


@router.delete("/{sprint_id}/tasks/{task_id}", response_model=SuccessResponse)
async def remove_task_from_sprint(
    sprint_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(SprintTask).where(SprintTask.sprint_id == sprint_id, SprintTask.task_id == task_id)
    )
    sprint_task = result.scalar_one_or_none()

    if not sprint_task:
        raise NotFoundException(message="任务不在此Sprint中")

    await db.delete(sprint_task)
    await db.commit()

    return SuccessResponse(message="任务已从Sprint中移除")


@router.get("/{sprint_id}/tasks")
async def list_sprint_tasks(
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """返回 Sprint 关联的任务列表（含任务详情）"""
    # 验证 sprint 存在
    spr = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    if not spr.scalar_one_or_none():
        raise NotFoundException(message="Sprint不存在")

    result = await db.execute(
        select(SprintTask, Task)
        .join(Task, SprintTask.task_id == Task.id)
        .where(SprintTask.sprint_id == sprint_id)
        .order_by(SprintTask.added_at)
    )
    rows = result.all()

    items = []
    for st, t in rows:
        items.append({
            "sprint_task_id": st.id,
            "task_id": t.id,
            "title": t.name or "",
            "status": t.status or st.status or "todo",
            "priority": getattr(t, 'priority', None),
            "story_points": getattr(t, 'story_points', None) or getattr(t, 'estimated_hours', None),
            "added_at": st.added_at.isoformat() if st.added_at else None,
            "completed_at": st.completed_at.isoformat() if st.completed_at else None,
        })

    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Sprint 报告 —— 燃尽图 + 燃起图 + 验收计划 + 任务摘要
# ---------------------------------------------------------------------------

@router.get("/{sprint_id}/report", response_model=SprintReportResponse)
async def get_sprint_report(
    sprint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    返回 Sprint 完整报告数据，供前端渲染：
    - burndown_data: 燃尽图（理想线 + 实际剩余）
    - burnup_data: 燃起图（scope 总量 + 累计完成）
    - tasks_summary: 关联任务摘要列表
    - acceptance_plan: 验收计划文本
    """
    sprint_result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = sprint_result.scalar_one_or_none()

    if not sprint:
        raise NotFoundException(message="Sprint不存在")

    # ---- 1) 查询关联任务及详情 ----
    task_result = await db.execute(
        select(SprintTask, Task)
        .join(Task, SprintTask.task_id == Task.id)
        .where(SprintTask.sprint_id == sprint_id)
    )
    rows = task_result.all()
    total_tasks = len(rows)

    # 按 completed_at / task.status 判定已完成
    completed_set = set()
    completion_dates = {}  # task_id -> date of completion
    for st, t in rows:
        is_done = (t.status == "done") or (st.status == "done")
        if is_done:
            completed_set.add(t.id)
            # 用 completed_at 或 actual_end 或 updated_at
            cd = st.completed_at
            if not cd and hasattr(t, 'actual_end') and t.actual_end:
                cd = t.actual_end
            if not cd and hasattr(t, 'updated_at') and t.updated_at:
                cd = t.updated_at
            if cd:
                completion_dates[t.id] = cd.date() if isinstance(cd, datetime) else cd

    completed_tasks = len(completed_set)

    # ---- 2) 构建任务摘要 ----
    tasks_summary = []
    for st, t in rows:
        tasks_summary.append({
            "task_id": t.id,
            "title": t.name or "(无标题)",
            "status": t.status or st.status or "todo",
            "priority": getattr(t, 'priority', None),
            "completed": t.id in completed_set,
        })

    # ---- 3) 燃尽数据（按日真实统计） ----
    burndown_data = []
    burnup_data = []

    if sprint.start_date and sprint.end_date:
        total_days = (sprint.end_date - sprint.start_date).days
        today = date.today()

        if total_days > 0 and total_tasks > 0:
            cumulative_completed = 0
            cumulative_total = total_tasks  # scope 起始值

            for i in range(total_days + 1):
                current_date = sprint.start_date + timedelta(days=i)
                is_future = current_date > today

                # 理想线：线性递减到 0
                ideal_remaining = max(0, round(total_tasks * (1 - i / total_days)))

                # 实际剩余：截止当天已完成数
                done_by_day = sum(
                    1 for tid in completed_set
                    if completion_dates.get(tid, date.max) <= current_date
                )
                actual_remaining = max(0, total_tasks - done_by_day)

                # 未来日期的实际线用理想线代替（避免"未卜先知"）
                if is_future:
                    actual_remaining = ideal_remaining

                burndown_data.append(SprintBurndownPoint(
                    date=current_date,
                    remaining=actual_remaining,
                    ideal=ideal_remaining,
                    actual=actual_remaining,
                ))

                # 燃起图数据
                ideal_completed = round(total_tasks * i / total_days)
                burnup_data.append(SprintBurnupPoint(
                    date=current_date,
                    total=cumulative_total,
                    completed=done_by_day,
                    ideal=ideal_completed,
                ))

    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return SprintReportResponse(
        sprint_id=sprint_id,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        burndown_data=burndown_data,
        burnup_data=burnup_data,
        velocity=sprint.velocity or 0,
        capacity=sprint.capacity or 0,
        completion_rate=round(completion_rate, 1),
        acceptance_plan=sprint.acceptance_plan,
        tasks_summary=tasks_summary,
    )

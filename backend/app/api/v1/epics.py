"""
[PMBOK KA: 范围管理 (Scope) — Epic管理、高层级需求分解]
对应PMI第6版标准：高层级需求分解、Epic管理
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import Epic, EpicTask, Task, User, Project
from app.schemas.epic import (
    EpicCreate, EpicUpdate, EpicResponse, EpicListResponse,
    EpicTaskCreate, EpicTaskResponse, EpicWithTasksResponse,
    EpicProgressUpdate, SuccessResponse
)
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

router = APIRouter()


@router.post("/", response_model=EpicResponse, status_code=201)
async def create_epic(
    epic_in: EpicCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project_result = await db.execute(
        select(Project).where(Project.id == epic_in.project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise NotFoundException(message="项目不存在")

    epic = Epic(
        name=epic_in.name,
        description=epic_in.description,
        color=epic_in.color,
        status=epic_in.status,
        project_id=epic_in.project_id,
        start_date=epic_in.start_date,
        end_date=epic_in.end_date,
        story_points_total=epic_in.story_points_total,
        story_points_completed=epic_in.story_points_completed,
        created_by=current_user.id,
    )

    db.add(epic)
    await db.commit()
    await db.refresh(epic)

    return epic


@router.get("/", response_model=EpicListResponse)
async def list_epics(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Epic)
    count_query = select(func.count(Epic.id))

    if project_id:
        query = query.where(Epic.project_id == project_id)
        count_query = count_query.where(Epic.project_id == project_id)

    if status:
        query = query.where(Epic.status == status)
        count_query = count_query.where(Epic.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Epic.created_at.desc())

    result = await db.execute(query)
    epics = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return EpicListResponse(
        items=[EpicResponse.model_validate(e) for e in epics],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{epic_id}", response_model=EpicWithTasksResponse)
async def get_epic(
    epic_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Epic).where(Epic.id == epic_id))
    epic = result.scalar_one_or_none()

    if not epic:
        raise NotFoundException(message="Epic不存在")

    task_result = await db.execute(
        select(EpicTask).where(EpicTask.epic_id == epic_id)
    )
    epic_tasks = task_result.scalars().all()

    task_count = len(epic_tasks)
    completed_task_count = 0

    if epic_tasks:
        task_ids = [et.task_id for et in epic_tasks]
        done_result = await db.execute(
            select(func.count(Task.id)).where(Task.id.in_(task_ids), Task.status == "done")
        )
        completed_task_count = done_result.scalar() or 0

    response = EpicWithTasksResponse.model_validate(epic)
    response.tasks = [EpicTaskResponse.model_validate(et) for et in epic_tasks]
    response.task_count = task_count
    response.completed_task_count = completed_task_count

    return response


@router.put("/{epic_id}", response_model=EpicResponse)
async def update_epic(
    epic_id: str,
    epic_in: EpicUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Epic).where(Epic.id == epic_id))
    epic = result.scalar_one_or_none()

    if not epic:
        raise NotFoundException(message="Epic不存在")

    update_data = epic_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(epic, field, value)

    epic.updated_at = datetime.now()

    await db.commit()
    await db.refresh(epic)

    return epic


@router.delete("/{epic_id}", response_model=SuccessResponse)
async def delete_epic(
    epic_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Epic).where(Epic.id == epic_id))
    epic = result.scalar_one_or_none()

    if not epic:
        raise NotFoundException(message="Epic不存在")

    await db.delete(epic)
    await db.commit()

    return SuccessResponse(message="Epic删除成功")


@router.post("/{epic_id}/tasks", response_model=EpicTaskResponse)
async def add_task_to_epic(
    epic_id: str,
    task_in: EpicTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    epic_result = await db.execute(select(Epic).where(Epic.id == epic_id))
    epic = epic_result.scalar_one_or_none()
    if not epic:
        raise NotFoundException(message="Epic不存在")

    task_result = await db.execute(select(Task).where(Task.id == task_in.task_id, Task.is_deleted == False))
    task = task_result.scalar_one_or_none()
    if not task:
        raise NotFoundException(message="任务不存在")

    existing_result = await db.execute(
        select(EpicTask).where(EpicTask.epic_id == epic_id, EpicTask.task_id == task_in.task_id)
    )
    if existing_result.scalar_one_or_none():
        raise ValidationException(message="任务已在此Epic中")

    epic_task = EpicTask(
        epic_id=epic_id,
        task_id=task_in.task_id
    )

    db.add(epic_task)
    await db.commit()
    await db.refresh(epic_task)

    return epic_task


@router.delete("/{epic_id}/tasks/{task_id}", response_model=SuccessResponse)
async def remove_task_from_epic(
    epic_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(EpicTask).where(EpicTask.epic_id == epic_id, EpicTask.task_id == task_id)
    )
    epic_task = result.scalar_one_or_none()

    if not epic_task:
        raise NotFoundException(message="任务不在此Epic中")

    await db.delete(epic_task)
    await db.commit()

    return SuccessResponse(message="任务已从Epic中移除")


@router.post("/{epic_id}/progress", response_model=EpicResponse)
async def update_epic_progress(
    epic_id: str,
    progress_in: EpicProgressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Epic).where(Epic.id == epic_id))
    epic = result.scalar_one_or_none()

    if not epic:
        raise NotFoundException(message="Epic不存在")

    epic.story_points_completed = progress_in.story_points_completed
    if epic.story_points_total > 0:
        epic.progress = min(100, (epic.story_points_completed / epic.story_points_total) * 100)
    epic.updated_at = datetime.now()

    await db.commit()
    await db.refresh(epic)

    return epic

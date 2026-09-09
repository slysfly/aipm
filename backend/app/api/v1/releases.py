"""
[PMBOK KA: 范围管理/进度管理 | PG: 规划 (Scope/Schedule/Planning) — 版本发布、里程碑]
对应PMI第6版标准：版本规划、里程碑管理
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from datetime import datetime, date

from app.db.session import get_db
from app.models import Release, ReleaseTask, Task, User, Project
from app.schemas.release import (
    ReleaseCreate, ReleaseUpdate, ReleaseResponse, ReleaseListResponse,
    ReleaseTaskCreate, ReleaseTaskResponse, ReleaseWithTasksResponse,
    SuccessResponse
)
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

router = APIRouter()


@router.post("/", response_model=ReleaseResponse, status_code=201)
async def create_release(
    release_in: ReleaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project_result = await db.execute(
        select(Project).where(Project.id == release_in.project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise NotFoundException(message="项目不存在")

    release = Release(
        name=release_in.name,
        version=release_in.version,
        description=release_in.description,
        status=release_in.status,
        project_id=release_in.project_id,
        release_date=release_in.release_date,
        created_by=current_user.id,
    )

    db.add(release)
    await db.commit()
    await db.refresh(release)

    return release


@router.get("/", response_model=ReleaseListResponse)
async def list_releases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Release)
    count_query = select(func.count(Release.id))

    if project_id:
        query = query.where(Release.project_id == project_id)
        count_query = count_query.where(Release.project_id == project_id)

    if status:
        query = query.where(Release.status == status)
        count_query = count_query.where(Release.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Release.created_at.desc())

    result = await db.execute(query)
    releases = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return ReleaseListResponse(
        items=[ReleaseResponse.model_validate(r) for r in releases],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{release_id}", response_model=ReleaseWithTasksResponse)
async def get_release(
    release_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Release).where(Release.id == release_id))
    release = result.scalar_one_or_none()

    if not release:
        raise NotFoundException(message="版本不存在")

    task_result = await db.execute(
        select(ReleaseTask).where(ReleaseTask.release_id == release_id)
    )
    release_tasks = task_result.scalars().all()

    task_count = len(release_tasks)
    completed_task_count = 0

    if release_tasks:
        task_ids = [rt.task_id for rt in release_tasks]
        done_result = await db.execute(
            select(func.count(Task.id)).where(Task.id.in_(task_ids), Task.status == "done")
        )
        completed_task_count = done_result.scalar() or 0

    response = ReleaseWithTasksResponse.model_validate(release)
    response.tasks = [ReleaseTaskResponse.model_validate(rt) for rt in release_tasks]
    response.task_count = task_count
    response.completed_task_count = completed_task_count

    return response


@router.put("/{release_id}", response_model=ReleaseResponse)
async def update_release(
    release_id: str,
    release_in: ReleaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Release).where(Release.id == release_id))
    release = result.scalar_one_or_none()

    if not release:
        raise NotFoundException(message="版本不存在")

    update_data = release_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(release, field, value)

    release.updated_at = datetime.now()

    await db.commit()
    await db.refresh(release)

    return release


@router.delete("/{release_id}", response_model=SuccessResponse)
async def delete_release(
    release_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Release).where(Release.id == release_id))
    release = result.scalar_one_or_none()

    if not release:
        raise NotFoundException(message="版本不存在")

    await db.delete(release)
    await db.commit()

    return SuccessResponse(message="版本删除成功")


@router.post("/{release_id}/tasks", response_model=ReleaseTaskResponse)
async def add_task_to_release(
    release_id: str,
    task_in: ReleaseTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    release_result = await db.execute(select(Release).where(Release.id == release_id))
    release = release_result.scalar_one_or_none()
    if not release:
        raise NotFoundException(message="版本不存在")

    task_result = await db.execute(select(Task).where(Task.id == task_in.task_id, Task.is_deleted == False))
    task = task_result.scalar_one_or_none()
    if not task:
        raise NotFoundException(message="任务不存在")

    existing_result = await db.execute(
        select(ReleaseTask).where(ReleaseTask.release_id == release_id, ReleaseTask.task_id == task_in.task_id)
    )
    if existing_result.scalar_one_or_none():
        raise ValidationException(message="任务已在此版本中")

    release_task = ReleaseTask(
        release_id=release_id,
        task_id=task_in.task_id
    )

    db.add(release_task)
    await db.commit()
    await db.refresh(release_task)

    return release_task


@router.delete("/{release_id}/tasks/{task_id}", response_model=SuccessResponse)
async def remove_task_from_release(
    release_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(ReleaseTask).where(ReleaseTask.release_id == release_id, ReleaseTask.task_id == task_id)
    )
    release_task = result.scalar_one_or_none()

    if not release_task:
        raise NotFoundException(message="任务不在此版本中")

    await db.delete(release_task)
    await db.commit()

    return SuccessResponse(message="任务已从版本中移除")


@router.post("/{release_id}/publish", response_model=ReleaseResponse)
async def publish_release(
    release_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Release).where(Release.id == release_id))
    release = result.scalar_one_or_none()

    if not release:
        raise NotFoundException(message="版本不存在")

    if release.status not in ["planning", "in_progress"]:
        raise ValidationException(message="当前状态不能发布")

    release.status = "released"
    release.release_date = date.today()
    release.updated_at = datetime.now()

    await db.commit()
    await db.refresh(release)

    return release


@router.post("/{release_id}/archive", response_model=ReleaseResponse)
async def archive_release(
    release_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(Release).where(Release.id == release_id))
    release = result.scalar_one_or_none()

    if not release:
        raise NotFoundException(message="版本不存在")

    if release.status != "released":
        raise ValidationException(message="只能归档已发布的版本")

    release.status = "archived"
    release.updated_at = datetime.now()

    await db.commit()
    await db.refresh(release)

    return release

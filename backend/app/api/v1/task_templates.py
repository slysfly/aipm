"""
[PMBOK KA: 范围管理 (Scope) — 任务模板、标准化WBS]
对应PMI第6版标准：WBS模板、标准化
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import TaskTemplate, Task, User, Project
from app.schemas.task_template import (
    TaskTemplateCreate, TaskTemplateUpdate, TaskTemplateResponse,
    TaskTemplateListResponse, TaskFromTemplateCreate,
    TaskTemplateFromTaskCreate, SuccessResponse
)
from app.schemas import TaskCreate, TaskResponse
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user

router = APIRouter()


@router.post("/", response_model=TaskTemplateResponse, status_code=201)
async def create_template(
    template_in: TaskTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if template_in.project_id:
        project_result = await db.execute(
            select(Project).where(Project.id == template_in.project_id, Project.is_deleted == False)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            raise NotFoundException(message="项目不存在")

    template = TaskTemplate(
        name=template_in.name,
        description=template_in.description,
        category=template_in.category,
        fields=template_in.fields,
        is_global=template_in.is_global,
        project_id=template_in.project_id,
        created_by=current_user.id,
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


@router.get("/", response_model=TaskTemplateListResponse)
async def list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    project_id: Optional[str] = None,
    category: Optional[str] = None,
    is_global: Optional[bool] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(TaskTemplate)
    count_query = select(func.count(TaskTemplate.id))

    if project_id:
        query = query.where(or_(TaskTemplate.project_id == project_id, TaskTemplate.is_global == True))
        count_query = count_query.where(or_(TaskTemplate.project_id == project_id, TaskTemplate.is_global == True))
    else:
        query = query.where(TaskTemplate.is_global == True)
        count_query = count_query.where(TaskTemplate.is_global == True)

    if category:
        query = query.where(TaskTemplate.category == category)
        count_query = count_query.where(TaskTemplate.category == category)

    if is_global is not None:
        query = query.where(TaskTemplate.is_global == is_global)
        count_query = count_query.where(TaskTemplate.is_global == is_global)

    if search:
        query = query.where(TaskTemplate.name.ilike(f"%{search}%"))
        count_query = count_query.where(TaskTemplate.name.ilike(f"%{search}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(TaskTemplate.created_at.desc())

    result = await db.execute(query)
    templates = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return TaskTemplateListResponse(
        items=[TaskTemplateResponse.model_validate(t) for t in templates],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{template_id}", response_model=TaskTemplateResponse)
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise NotFoundException(message="模板不存在")

    return template


@router.put("/{template_id}", response_model=TaskTemplateResponse)
async def update_template(
    template_id: str,
    template_in: TaskTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise NotFoundException(message="模板不存在")

    update_data = template_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    template.updated_at = datetime.now()

    await db.commit()
    await db.refresh(template)

    return template


@router.delete("/{template_id}", response_model=SuccessResponse)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise NotFoundException(message="模板不存在")

    await db.delete(template)
    await db.commit()

    return SuccessResponse(message="模板删除成功")


@router.post("/{template_id}/create-task", response_model=TaskResponse)
async def create_task_from_template(
    template_id: str,
    task_in: TaskFromTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    template_result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == template_id))
    template = template_result.scalar_one_or_none()
    if not template:
        raise NotFoundException(message="模板不存在")

    project_result = await db.execute(
        select(Project).where(Project.id == task_in.project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        raise NotFoundException(message="项目不存在")

    fields = template.fields or {}
    task_name = task_in.name or template.name

    task = Task(
        project_id=task_in.project_id,
        name=task_name,
        description=template.description or fields.get("description"),
        estimated_hours=fields.get("estimated_hours", 0),
        priority=fields.get("priority", 3),
        status=fields.get("status", "todo"),
        labels=fields.get("labels", []),
        category=template.category,
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    return task


@router.post("/from-task", response_model=TaskTemplateResponse)
async def create_template_from_task(
    data: TaskTemplateFromTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task_result = await db.execute(select(Task).where(Task.id == data.task_id, Task.is_deleted == False))
    task = task_result.scalar_one_or_none()
    if not task:
        raise NotFoundException(message="任务不存在")

    template = TaskTemplate(
        name=data.name,
        description=task.description,
        category=data.category or task.category,
        fields={
            "estimated_hours": float(task.estimated_hours) if task.estimated_hours else 0,
            "priority": task.priority,
            "status": task.status,
            "labels": task.labels or [],
        },
        is_global=data.is_global,
        project_id=task.project_id,
        created_by=current_user.id,
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


@router.post("/{template_id}/copy", response_model=TaskTemplateResponse)
async def copy_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise NotFoundException(message="模板不存在")

    new_template = TaskTemplate(
        name=f"{template.name} (副本)",
        description=template.description,
        category=template.category,
        fields=template.fields,
        is_global=template.is_global,
        project_id=template.project_id,
        created_by=current_user.id,
    )

    db.add(new_template)
    await db.commit()
    await db.refresh(new_template)

    return new_template

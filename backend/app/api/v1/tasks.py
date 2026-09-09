"""
PMI中国AI项目管理社区 - 任务API路由

[PMBOK KA: 范围管理/进度管理 (Scope/Schedule) — WBS创建、任务依赖、关键路径、甘特图]
对应PMI第6版标准：创建WBS、定义活动、排列活动顺序、估算活动持续时间、制定进度计划

PMBOK 7th Principle: Quality/Delivery | Domain: Planning/Project Work — WBS、质量融入交付物
PMBOK 8th: Data-Driven Task Management"""

import logging
from fastapi import APIRouter, Depends, Query, Header, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import Task, User, TaskDependency, Project
from app.schemas import (
    TaskCreate, TaskUpdate, TaskResponse, TaskListResponse,
    TaskDependencyCreate, TaskDependencyResponse,
    SuccessResponse, PageParams
)
from app.core.exceptions import NotFoundException, ValidationException, CircularDependencyException
from app.core.security import get_current_user, require_task_membership, require_project_access_optional
from app.services.cpm import GanttAlgorithmService

logger = logging.getLogger(__name__)
from app.services.zapier_integration import notify_zapier_event, ZapierEventType
from app.services.automation_trigger import (
    trigger_task_created,
    trigger_task_updated,
    trigger_status_changed,
)
from app.services.webhook_service import trigger_webhook_event
from app.schemas.webhook import WebhookEvent

router = APIRouter()


def generate_wbs_code(parent_code: Optional[str], sibling_count: int) -> str:
    if parent_code:
        return f"{parent_code}.{sibling_count}"
    else:
        return str(sibling_count)


@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(
    task_in: TaskCreate,
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
    
    # 计算WBS编码
    if task_in.parent_task_id:
        parent_result = await db.execute(
            select(Task).where(Task.id == task_in.parent_task_id)
        )
        parent = parent_result.scalar_one_or_none()
        parent_code = parent.wbs_code if parent else None
        parent_level = parent.level if parent else 0
        
        # 统计同级兄弟任务数量
        sibling_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == task_in.project_id,
                Task.parent_task_id == task_in.parent_task_id,
                Task.is_deleted == False
            )
        )
        sibling_count = sibling_result.scalar() + 1
    else:
        parent_code = None
        parent_level = 0
        
        # 统计根级任务数量
        sibling_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == task_in.project_id,
                Task.parent_task_id == None,
                Task.is_deleted == False
            )
        )
        sibling_count = sibling_result.scalar() + 1
    
    wbs_code = generate_wbs_code(parent_code, sibling_count)
    
    # 创建任务
    task = Task(
        project_id=task_in.project_id,
        parent_task_id=task_in.parent_task_id,
        wbs_code=wbs_code,
        name=task_in.name,
        description=task_in.description,
        level=parent_level + 1,
        estimated_hours=task_in.estimated_hours,
        planned_start=task_in.planned_start,
        planned_end=task_in.planned_end,
        priority=task_in.priority,
        status=task_in.status,
        assignee_id=task_in.assignee_id,
        is_milestone=task_in.is_milestone,
        labels=task_in.labels,
        category=task_in.category,
        sprint_id=task_in.sprint_id,
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # ── AI 下一步行动建议：创建时立即生成 ────────────────────────
    try:
        from app.services.next_action_service import (
            generate_next_action, compute_source_hash,
        )
        suggestion = await generate_next_action(task)
        task.next_action_suggestion = suggestion
        task.next_action_generated_at = datetime.now()
        task.next_action_source_hash = compute_source_hash(task)
        await db.commit()
    except Exception as e:
        logger.warning("生成任务 next_action 失败（已忽略）: %s", e, exc_info=True)

    # 级联完成：任务归属的 Sprint / 项目自动推导（全部完成→completed）
    try:
        from app.services.completion_service import recompute_after_task_change
        await recompute_after_task_change(db, new_sprint_id=task.sprint_id, new_project_id=task.project_id)
        await db.commit()
    except Exception as e:
        logger.warning("级联完成计算失败（已忽略）: %s", e, exc_info=True)

    # 自动知识沉淀（AutoRAG）：将新建任务自动入库供 AI 检索
    try:
        from app.services.knowledge_auto_service import auto_ingest
        _content = (
            f"任务：{task.name}\n"
            f"描述：{task.description or ''}\n状态：{task.status}\n优先级：{task.priority}"
        )
        await auto_ingest(db, "task", task.name, _content, project_id=task.project_id, created_by=current_user.id)
    except Exception as e:
        logger.warning("任务自动知识沉淀失败（已忽略）: %s", e, exc_info=True)

    # 预加载关系，避免响应序列化时触发异步懒加载（session 关闭后导致 MissingGreenlet）
    # 注意：async 模式下 refresh(attribute_names=关系) 会触发 greenlet_spawn 错误，
    # 必须用 selectinload 重新查询来加载关系。
    task = (await db.execute(
        select(Task)
        .where(Task.id == task.id)
        .options(selectinload(Task.subtasks), selectinload(Task.dependencies_from), selectinload(Task.assignee))
    )).scalar_one()

    # 触发Zapier webhook - 任务创建
    try:
        await notify_zapier_event(
            ZapierEventType.TASK_CREATED,
            {
                "id": task.id,
                "name": task.name,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
                "project_id": task.project_id,
                "assignee_id": task.assignee_id,
                "wbs_code": task.wbs_code,
                "level": task.level,
                "estimated_hours": float(task.estimated_hours) if task.estimated_hours else 0,
                "planned_start": task.planned_start.isoformat() if task.planned_start else None,
                "planned_end": task.planned_end.isoformat() if task.planned_end else None,
                "labels": task.labels,
                "category": task.category,
                "is_milestone": task.is_milestone,
                "created_at": task.created_at.isoformat() if task.created_at else None,
            }
        )
    except Exception as e:
        logger.warning("任务创建 Zapier webhook 触发失败（已忽略）: %s", e, exc_info=True)

    # 触发自动化规则（创建事件）
    try:
        await trigger_task_created(db, task)
    except Exception as e:
        logger.warning(f"自动化规则触发失败(任务创建): {e}")

    # 触发Webhook事件（任务创建）
    try:
        await trigger_webhook_event(
            db,
            WebhookEvent.TASK_CREATED,
            {
                "event": "task.created",
                "data": {
                    "id": task.id,
                    "name": task.name,
                    "status": task.status,
                    "priority": task.priority,
                    "project_id": task.project_id,
                    "assignee_id": task.assignee_id,
                    "wbs_code": task.wbs_code,
                },
                "timestamp": task.created_at.isoformat() if task.created_at else None,
            },
            project_id=task.project_id,
        )
    except Exception as e:
        logger.warning(f"Webhook事件触发失败(任务创建): {e}")

    return task


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    project_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assignee_id: Optional[str] = None,
    search: Optional[str] = None,
    _: None = Depends(require_project_access_optional),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(Task).where(Task.is_deleted == False).options(
        selectinload(Task.subtasks).selectinload(Task.subtasks),
        selectinload(Task.subtasks).selectinload(Task.dependencies_from),
        selectinload(Task.dependencies_from),
        selectinload(Task.assignee)
    )
    count_query = select(func.count(Task.id)).where(Task.is_deleted == False)
    
    # 筛选条件
    if project_id:
        query = query.where(Task.project_id == project_id)
        count_query = count_query.where(Task.project_id == project_id)
    
    if parent_task_id is not None:
        if parent_task_id:
            query = query.where(Task.parent_task_id == parent_task_id)
            count_query = count_query.where(Task.parent_task_id == parent_task_id)
        else:
            query = query.where(Task.parent_task_id == None)
            count_query = count_query.where(Task.parent_task_id == None)
    
    if status:
        query = query.where(Task.status == status)
        count_query = count_query.where(Task.status == status)
    
    if priority:
        query = query.where(Task.priority == priority)
        count_query = count_query.where(Task.priority == priority)
    
    if assignee_id:
        query = query.where(Task.assignee_id == assignee_id)
        count_query = count_query.where(Task.assignee_id == assignee_id)
    
    if search:
        query = query.where(Task.name.ilike(f"%{search}%"))
        count_query = count_query.where(Task.name.ilike(f"%{search}%"))

    # 获取总数
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # 分页查询
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Task.sort_order, Task.created_at)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    total_pages = (total + page_size - 1) // page_size
    
    return TaskListResponse(
        items=[TaskResponse.model_validate(t) for t in tasks],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_task_membership),
    response: Response = None,
):
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id, Task.is_deleted == False)
        .options(selectinload(Task.subtasks), selectinload(Task.dependencies_from), selectinload(Task.assignee))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException(message="任务不存在")

    if response is not None:
        response.headers["X-Entity-Version"] = str(task.version or 1)
    return task


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    task_in: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_task_membership),
    response: Response = None,
    x_base_version: Optional[int] = Header(None, alias="X-Base-Version"),
):
    result = await db.execute(
        select(Task)
        .where(Task.id == task_id, Task.is_deleted == False)
        .options(selectinload(Task.subtasks), selectinload(Task.dependencies_from), selectinload(Task.assignee))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException(message="任务不存在")

    # 乐观锁：离线编辑回放时携带 X-Base-Version；与最新版本不一致说明
    # 服务端已被其他人/其他端修改，返回 409 交由前端冲突合并流程处理。
    if x_base_version is not None and int(x_base_version) != (task.version or 1):
        server_data = {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "progress": float(task.progress) if task.progress else 0,
            "assignee_id": task.assignee_id,
            "planned_start": task.planned_start.isoformat() if task.planned_start else None,
            "planned_end": task.planned_end.isoformat() if task.planned_end else None,
            "version": task.version or 1,
        }
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "conflict",
                "message": "该任务已被其他人修改，请解决冲突后重试",
                "entity": "task",
                "entity_id": task.id,
                "server_version": task.version or 1,
                "server_data": server_data,
            },
        )

    # 记录旧状态用于自动化触发
    old_status = task.status

    # 记录旧归属用于级联完成重算（任务可能改派 Sprint / 项目）
    old_sprint_id = task.sprint_id
    old_project_id = task.project_id

    # ── AI 下一步行动建议：变更前抓旧指纹，变更后若关键字段变化则重新生成 ──
    try:
        from app.services.next_action_service import (
            generate_next_action, compute_source_hash,
        )
        prev_hash = compute_source_hash(task)
    except Exception:
        prev_hash = None

    # 更新字段
    update_data = task_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    task.updated_at = datetime.now()
    # 乐观锁版本自增（无并发写时默认从 1 起算）
    task.version = (task.version or 1) + 1

    await db.commit()
    await db.refresh(task)

    # ── 重新生成 next_action（仅当关键字段指纹变化） ─────────────
    try:
        from app.services.next_action_service import (
            generate_next_action, compute_source_hash,
        )
        new_hash = compute_source_hash(task)
        if prev_hash != new_hash:
            suggestion = await generate_next_action(task)
            task.next_action_suggestion = suggestion
            task.next_action_generated_at = datetime.now()
            task.next_action_source_hash = new_hash
            await db.commit()
    except Exception as e:
        logger.warning("重新生成 next_action 失败（已忽略）: %s", e, exc_info=True)

    # 级联完成：任务归属变更后重算涉及的 Sprint / 项目
    try:
        from app.services.completion_service import recompute_after_task_change
        await recompute_after_task_change(
            db,
            old_sprint_id=old_sprint_id,
            old_project_id=old_project_id,
            new_sprint_id=task.sprint_id,
            new_project_id=task.project_id,
        )
        await db.commit()
    except Exception as e:
        logger.warning("级联完成计算失败（已忽略）: %s", e, exc_info=True)

    if response is not None:
        response.headers["X-Entity-Version"] = str(task.version or 1)
    # 预加载关系，避免响应序列化时触发异步懒加载
    task = (await db.execute(
        select(Task)
        .where(Task.id == task.id)
        .options(selectinload(Task.subtasks), selectinload(Task.dependencies_from), selectinload(Task.assignee))
    )).scalar_one()

    # 触发Zapier webhook - 任务更新
    try:
        event_type = ZapierEventType.TASK_COMPLETED if task.status == "done" else ZapierEventType.TASK_UPDATED
        await notify_zapier_event(
            event_type,
            {
                "id": task.id,
                "name": task.name,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
                "project_id": task.project_id,
                "assignee_id": task.assignee_id,
                "wbs_code": task.wbs_code,
                "level": task.level,
                "estimated_hours": float(task.estimated_hours) if task.estimated_hours else 0,
                "actual_hours": float(task.actual_hours) if task.actual_hours else 0,
                "progress": float(task.progress) if task.progress else 0,
                "planned_start": task.planned_start.isoformat() if task.planned_start else None,
                "planned_end": task.planned_end.isoformat() if task.planned_end else None,
                "actual_start": task.actual_start.isoformat() if task.actual_start else None,
                "actual_end": task.actual_end.isoformat() if task.actual_end else None,
                "labels": task.labels,
                "category": task.category,
                "is_milestone": task.is_milestone,
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            }
        )
    except Exception as e:
        logger.warning("任务更新 Zapier webhook 触发失败（已忽略）: %s", e, exc_info=True)

    # 触发自动化规则（状态变更 / 更新）
    try:
        if old_status != task.status:
            await trigger_status_changed(db, task, old_status, task.status)
        else:
            await trigger_task_updated(db, task)
    except Exception as e:
        logger.warning(f"自动化规则触发失败(任务更新): {e}")

    # 触发Webhook事件（任务更新/完成）
    try:
        webhook_event = WebhookEvent.TASK_COMPLETED if task.status == "done" else WebhookEvent.TASK_UPDATED
        await trigger_webhook_event(
            db,
            webhook_event,
            {
                "event": "task.updated" if task.status != "done" else "task.completed",
                "data": {
                    "id": task.id,
                    "name": task.name,
                    "status": task.status,
                    "priority": task.priority,
                    "project_id": task.project_id,
                    "assignee_id": task.assignee_id,
                    "progress": float(task.progress) if task.progress else 0,
                    "wbs_code": task.wbs_code,
                },
                "timestamp": task.updated_at.isoformat() if task.updated_at else None,
            },
            project_id=task.project_id,
        )
    except Exception as e:
        logger.warning(f"Webhook事件触发失败(任务更新): {e}")

    return task


@router.post("/{task_id}/next-action/regenerate")
async def regenerate_next_action(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_task_membership),
):
    """强制重新生成任务的"下一步行动"建议。

    - 不依赖外部 LLM，纯规则引擎。
    - 写入 next_action_suggestion / next_action_generated_at / next_action_source_hash。
    - 返回最新建议 + 生成时间，便于前端即时刷新。
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.is_deleted == False)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundException(message="任务不存在")

    try:
        from app.services.next_action_service import (
            generate_next_action, compute_source_hash,
        )
        suggestion = await generate_next_action(task)
        task.next_action_suggestion = suggestion
        task.next_action_generated_at = datetime.now()
        task.next_action_source_hash = compute_source_hash(task)
        await db.commit()
        await db.refresh(task)
        return {
            "success": True,
            "task_id": task.id,
            "suggestion": suggestion,
            "generated_at": task.next_action_generated_at.isoformat() if task.next_action_generated_at else None,
        }
    except Exception as e:
        logger.exception("重新生成 next_action 异常: %s", e)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "regenerate_failed", "message": str(e)},
        )


@router.delete("/{task_id}", response_model=SuccessResponse)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_task_membership)
):
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.is_deleted == False)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise NotFoundException(message="任务不存在")

    # 记录旧归属用于级联完成重算（软删除后不再计入原 Sprint / 项目）
    old_sprint_id = task.sprint_id
    old_project_id = task.project_id

    # 软删除
    task.is_deleted = True
    task.deleted_at = datetime.now()

    await db.commit()

    # 级联完成：任务移除后重算原 Sprint / 项目
    try:
        from app.services.completion_service import recompute_after_task_change
        await recompute_after_task_change(db, old_sprint_id=old_sprint_id, old_project_id=old_project_id)
        await db.commit()
    except Exception as e:
        logger.warning("级联完成计算失败（已忽略）: %s", e, exc_info=True)

    return SuccessResponse(message="任务删除成功")


@router.post("/{task_id}/dependencies", response_model=TaskDependencyResponse)
async def create_task_dependency(
    task_id: str,
    dependency_in: TaskDependencyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 验证前置任务存在
    pred_result = await db.execute(
        select(Task).where(Task.id == dependency_in.predecessor_id, Task.is_deleted == False)
    )
    predecessor = pred_result.scalar_one_or_none()
    if not predecessor:
        raise NotFoundException(message="前置任务不存在")
    
    # 验证后继任务存在
    succ_result = await db.execute(
        select(Task).where(Task.id == dependency_in.successor_id, Task.is_deleted == False)
    )
    successor = succ_result.scalar_one_or_none()
    if not successor:
        raise NotFoundException(message="后继任务不存在")
    
    # 检查是否会产生循环依赖
    deps_result = await db.execute(
        select(TaskDependency).where(
            or_(
                TaskDependency.predecessor_id == dependency_in.successor_id,
                TaskDependency.successor_id == dependency_in.predecessor_id
            )
        )
    )
    existing_deps = deps_result.scalars().all()
    
    # 简化的循环依赖检测
    dep_dicts = [
        {"predecessor_id": d.predecessor_id, "successor_id": d.successor_id}
        for d in existing_deps
    ]
    
    # 获取所有任务
    all_tasks_result = await db.execute(select(Task.id).where(Task.is_deleted == False))
    all_task_ids = [t[0] for t in all_tasks_result.all()]
    
    # 检测循环
    cycles = GanttAlgorithmService.detect_circular_dependencies(
        all_task_ids,
        [(d['predecessor_id'], d['successor_id']) for d in dep_dicts] + 
        [(dependency_in.predecessor_id, dependency_in.successor_id)]
    )
    
    if cycles:
        raise CircularDependencyException(
            message="添加该依赖会形成循环依赖",
            details={"cycles": cycles}
        )
    
    # 创建依赖
    dependency = TaskDependency(
        predecessor_id=dependency_in.predecessor_id,
        successor_id=dependency_in.successor_id,
        dependency_type=dependency_in.dependency_type,
        lag_time=dependency_in.lag_time
    )
    
    db.add(dependency)
    await db.commit()
    await db.refresh(dependency)
    
    return dependency


@router.delete("/{task_id}/dependencies/{dependency_id}")
async def delete_task_dependency(
    task_id: str,
    dependency_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除任务依赖关系"""
    dep = await db.get(TaskDependency, dependency_id)
    if not dep:
        raise NotFoundException(message="依赖关系不存在")
    if dep.successor_id != task_id:
        raise BadRequestException(message="该依赖不属于此任务")
    await db.delete(dep)
    await db.commit()
    return {"ok": True, "message": "依赖关系已删除"}


@router.get("/{task_id}/subtasks")
async def get_task_subtasks(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Task)
        .where(Task.parent_task_id == task_id, Task.is_deleted == False)
        .options(selectinload(Task.subtasks), selectinload(Task.dependencies_from), selectinload(Task.assignee))
        .order_by(Task.sort_order, Task.created_at)
    )
    subtasks = result.scalars().all()
    
    return [TaskResponse.model_validate(t) for t in subtasks]

"""
PMI中国AI项目管理社区 - 项目API路由

[PMBOK KA: 整合管理 (Integration Management) — 项目章程制定、项目管理计划整合、项目组合管理]
对应PMI第6版标准：整合项目管理、项目章程制定、项目管理计划整合

PMBOK 7th Principle: Stewardship/Value | Domain: Delivery — 项目章程、价值交付、项目管理计划整合
PMBOK 8th: Business Acumen/Strategic Alignment"""

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, Integer, or_, case
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime, date, timedelta
from math import ceil

from app.db.session import get_db
from app.models import Project, User, Task, Risk, Milestone
from app.models.pm_extras import Lesson, ChangeRequest
from app.models.permission import ProjectMember
from app.services.knowledge_linkage import archive_lesson_to_knowledge
from app.services.ai.out_of_box_agents import _llm, _safe_json
from app.services.async_task_runner import dispatch_task, register_handler
from app.models.async_task import AsyncTask, AsyncTaskStatus
from app.schemas import (
    ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse,
    SuccessResponse, PageParams
)
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user, require_project_membership
from app.core.responses import success, fail
from app.services.zapier_integration import notify_zapier_event, ZapierEventType
from app.services.webhook_service import trigger_webhook_event
from app.services.cpm import GanttAlgorithmService
from app.schemas.webhook import WebhookEvent

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(
    project_in: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 创建项目
    project = Project(
        name=project_in.name,
        description=project_in.description,
        industry_type=project_in.industry_type,
        project_type=project_in.project_type,
        priority=project_in.priority,
        color=project_in.color,
        start_date=project_in.start_date,
        end_date=project_in.end_date,
        baseline_start=project_in.baseline_start,
        baseline_end=project_in.baseline_end,
        budget=project_in.budget,
        baseline_budget=project_in.baseline_budget,
        portfolio_id=project_in.portfolio_id,
        owner_id=project_in.owner_id or current_user.id,
    )
    
    db.add(project)
    await db.commit()
    await db.refresh(project)

    # 自动知识沉淀（AutoRAG）：将新建项目自动入库供 AI 检索
    try:
        from app.services.knowledge_auto_service import auto_ingest
        _content = (
            f"项目名称：{project.name}\n"
            f"描述：{project.description or ''}\n"
            f"行业：{project.industry_type}\n类型：{project.project_type}\n优先级：{project.priority}"
        )
        await auto_ingest(db, "project", project.name, _content, project_id=project.id, created_by=current_user.id)
    except Exception as e:
        logger.warning("项目自动知识沉淀失败（已忽略）: %s", e, exc_info=True)

    # 触发Zapier webhook - 项目创建
    try:
        await notify_zapier_event(
            ZapierEventType.PROJECT_CREATED,
            {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "status": project.status,
                "priority": project.priority,
                "color": project.color,
                "owner_id": project.owner_id,
                "industry_type": project.industry_type,
                "project_type": project.project_type,
                "start_date": project.start_date.isoformat() if project.start_date else None,
                "end_date": project.end_date.isoformat() if project.end_date else None,
                "budget": float(project.budget) if project.budget else 0,
                "portfolio_id": project.portfolio_id,
                "created_at": project.created_at.isoformat() if project.created_at else None,
            }
        )
    except Exception as e:
        logger.warning("项目创建 Zapier webhook 触发失败（已忽略）: %s", e, exc_info=True)

    # 触发Webhook事件（项目创建）
    try:
        await trigger_webhook_event(
            db,
            WebhookEvent.PROJECT_CREATED,
            {
                "event": "project.created",
                "data": {
                    "id": project.id,
                    "name": project.name,
                    "status": project.status,
                    "owner_id": project.owner_id,
                    "portfolio_id": project.portfolio_id,
                },
                "timestamp": project.created_at.isoformat() if project.created_at else None,
            },
            project_id=project.id,
        )
    except Exception as e:
        logger.warning(f"Webhook事件触发失败(项目创建): {e}")

    # 预加载 owner 关系，避免响应序列化时触发异步懒加载
    project = (await db.execute(
        select(Project).where(Project.id == project.id).options(selectinload(Project.owner))
    )).scalar_one()
    return project


@router.get("/", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    portfolio_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 构建查询
    query = select(Project).where(Project.is_deleted == False).options(selectinload(Project.owner))
    count_query = select(func.count(Project.id)).where(Project.is_deleted == False)

    # 对象级鉴权：非管理员仅可见自己拥有或参与的项目
    if not current_user.is_superuser:
        member_subq = select(ProjectMember.project_id).where(
            ProjectMember.user_id == current_user.id,
            ProjectMember.is_active == True,
        )
        access_filter = or_(Project.owner_id == current_user.id, Project.id.in_(member_subq))
        query = query.where(access_filter)
        count_query = count_query.where(access_filter)
    
    # 添加筛选条件
    if search:
        query = query.where(Project.name.ilike(f"%{search}%"))
        count_query = count_query.where(Project.name.ilike(f"%{search}%"))
    
    if status:
        query = query.where(Project.status == status)
        count_query = count_query.where(Project.status == status)
    
    if priority:
        query = query.where(Project.priority == priority)
        count_query = count_query.where(Project.priority == priority)
    
    if portfolio_id:
        query = query.where(Project.portfolio_id == portfolio_id)
        count_query = count_query.where(Project.portfolio_id == portfolio_id)
    
    # 获取总数
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # 分页查询
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Project.updated_at.desc())
    
    result = await db.execute(query)
    projects = result.scalars().all()
    
    # 计算分页信息
    total_pages = (total + page_size - 1) // page_size
    
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_membership)
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False).options(selectinload(Project.owner))
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise NotFoundException(message="项目不存在")
    
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    project_in: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_membership)
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False).options(selectinload(Project.owner))
    )
    project = result.scalar_one_or_none()

    if not project:
        raise NotFoundException(message="项目不存在")

    # 仅管理员可变更项目所有者（防越权转让）
    if project_in.owner_id is not None and project_in.owner_id != project.owner_id:
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="仅管理员可变更项目所有者",
            )

    # 更新字段
    update_data = project_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    project.updated_at = datetime.now()

    await db.commit()
    await db.refresh(project)

    # 预加载 owner 关系
    project = (await db.execute(
        select(Project).where(Project.id == project.id).options(selectinload(Project.owner))
    )).scalar_one()
    return project


@router.delete("/{project_id}", response_model=SuccessResponse)
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_membership)
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise NotFoundException(message="项目不存在")
    
    # 仅项目所有者或管理员可删除（防成员越权删除）
    if not current_user.is_superuser and project.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅项目所有者或管理员可删除项目",
        )
    
    # 软删除
    project.is_deleted = True
    project.deleted_at = datetime.now()
    
    await db.commit()
    
    return SuccessResponse(message="项目删除成功")


@router.get("/{project_id}/statistics")
async def get_project_statistics(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_membership)
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise NotFoundException(message="项目不存在")
    
    # 统计任务数量
    task_stats_result = await db.execute(
        select(
            func.count(Task.id).label("total"),
            func.sum(case((Task.status == 'done', 1), else_=0)).label("completed"),
        ).where(Task.project_id == project_id, Task.is_deleted == False)
    )
    task_stats = task_stats_result.one()
    
    # 统计逾期任务
    overdue_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id,
            Task.is_deleted == False,
            Task.planned_end < datetime.now(),
            Task.status != 'done'
        )
    )
    overdue_count = overdue_result.scalar()
    
    return success(data={
        "task_count": task_stats.total or 0,
        "completed_task_count": task_stats.completed or 0,
        "overdue_task_count": overdue_count or 0,
        "progress": (task_stats.completed / task_stats.total * 100) if task_stats.total > 0 else 0
    })


@router.get("/{project_id}/critical-path")
async def get_project_critical_path(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    关键路径法（CPM）路线图数据（PMBOK 增强版）。
    支持 FS/FF/SS/SF 四种依赖关系 + 正负延隔。
    返回完整 CPM 数据 + 甘特图条形数据 + AON 网络图数据。
    """
    from app.services.cpm import GanttAlgorithmService

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise NotFoundException(message="项目不存在")

    tasks_res = await db.execute(
        select(Task)
        .where(Task.project_id == project_id, Task.is_deleted == False, Task.is_milestone == False)
        .options(selectinload(Task.dependencies_from), selectinload(Task.assignee))
    )
    tasks = tasks_res.scalars().all()

    if not tasks:
        return success(data={
            "project_id": project_id,
            "project_name": project.name,
            "anchor_date": None,
            "project_duration_days": 0,
            "has_dependencies": False,
            "task_count": 0,
            "tasks": [],
            "critical_path": [],
            "critical_path_names": [],
            "gantt_data": [],
            "network_data": {"nodes": [], "edges": [], "layout": {}},
        })

    def _duration(t: Task) -> int:
        if t.planned_start and t.planned_end:
            days = (t.planned_end - t.planned_start).days
            if days and days > 0:
                return max(1, int(days))
        if t.estimated_hours and float(t.estimated_hours) > 0:
            return max(1, int(ceil(float(t.estimated_hours) / 8)))
        return 1

    tdicts: List[Dict] = []
    depdicts: List[Dict] = []
    for t in tasks:
        tdicts.append({"id": t.id, "name": t.name, "duration": _duration(t)})
        for d in t.dependencies_from:
            depdicts.append({
                "predecessor_id": d.predecessor_id,
                "successor_id": d.successor_id,
                "dependency_type": d.dependency_type or "FS",
                "lag_time": d.lag_time or 0,
            })

    result = GanttAlgorithmService.compute_cpm_schedule(tdicts, depdicts)
    cpm_nodes = result["tasks"]
    ordered = result["critical_path"]
    project_end = result["project_end"]
    deps = result.get("dependencies", [])

    # 锚定日期
    anchor: date = project.start_date
    if anchor is None:
        planned = [t.planned_start.date() for t in tasks if t.planned_start]
        anchor = min(planned) if planned else date.today()

    name_by_id = {t.id: t.name for t in tasks}
    critical_set = set(ordered)

    # 任务详情映射
    task_extra: Dict[str, Dict] = {}
    out_tasks: List[Dict] = []
    for t in tasks:
        node = cpm_nodes[t.id]
        start = anchor + timedelta(days=node.earliest_start)
        end = anchor + timedelta(days=node.earliest_finish)
        assignee = None
        if t.assignee:
            assignee = t.assignee.full_name or t.assignee.username
        task_dict = {
            "id": t.id,
            "name": t.name,
            "wbs_code": t.wbs_code,
            "duration_days": node.duration,
            "es": node.earliest_start,
            "ef": node.earliest_finish,
            "ls": node.latest_start,
            "lf": node.latest_finish,
            "total_float": node.total_float,
            "free_float": node.free_float,
            "is_critical": node.is_critical,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "progress": float(t.progress or 0),
            "status": t.status,
            "priority": t.priority,
            "assignee_name": assignee,
            "dependency_ids": [d.predecessor_id for d in t.dependencies_from],
        }
        out_tasks.append(task_dict)
        task_extra[t.id] = {
            "name": t.name,
            "progress": float(t.progress or 0),
            "status": t.status,
            "wbs_code": t.wbs_code,
            "priority": t.priority,
            "assignee_name": assignee,
            "dependency_ids": [d.predecessor_id for d in t.dependencies_from],
        }

    # 排序
    out_tasks.sort(key=lambda x: (x["es"], not x["is_critical"], x["wbs_code"] or "zzz", x["name"]))
    critical_names = [name_by_id[i] for i in ordered if i in name_by_id]

    # ═══ 生成甘特图数据 ═══
    gantt_data = GanttAlgorithmService.generate_gantt_bar_data(
        cpm_nodes, anchor, task_extra, critical_set
    )

    # ═══ 生成 AON 网络图数据 ═══
    network_data = GanttAlgorithmService.generate_network_diagram_data(
        cpm_nodes, deps, name_by_id, task_extra
    )

    return {
        "project_id": project_id,
        "project_name": project.name,
        "anchor_date": anchor.isoformat(),
        "project_duration_days": project_end,
        "has_dependencies": len(depdicts) > 0,
        "task_count": len(out_tasks),
        "tasks": out_tasks,
        "critical_path": ordered,
        "critical_path_names": critical_names,
        "gantt_data": gantt_data,
        "network_data": network_data,
    }


@router.get("/{project_id}/network-diagram")
async def get_project_network_diagram(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取项目 AON 紧前逻辑关系图数据（PMBOK Precedence Diagramming Method）。
    单独端点，供前端 Tab 切换时按需加载。
    """
    from app.services.cpm import GanttAlgorithmService

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise NotFoundException(message="项目不存在")

    tasks_res = await db.execute(
        select(Task)
        .where(Task.project_id == project_id, Task.is_deleted == False, Task.is_milestone == False)
        .options(selectinload(Task.dependencies_from), selectinload(Task.assignee))
    )
    tasks = tasks_res.scalars().all()

    if not tasks:
        return {"nodes": [], "edges": [], "layout": {"width": 800, "height": 600, "levels": 0}}

    def _duration(t: Task) -> int:
        if t.planned_start and t.planned_end:
            days = (t.planned_end - t.planned_start).days
            if days and days > 0:
                return max(1, int(days))
        if t.estimated_hours and float(t.estimated_hours) > 0:
            return max(1, int(ceil(float(t.estimated_hours) / 8)))
        return 1

    tdicts = [{"id": t.id, "name": t.name, "duration": _duration(t)} for t in tasks]
    depdicts = []
    for t in tasks:
        for d in t.dependencies_from:
            depdicts.append({
                "predecessor_id": d.predecessor_id,
                "successor_id": d.successor_id,
                "dependency_type": d.dependency_type or "FS",
                "lag_time": d.lag_time or 0,
            })

    result = GanttAlgorithmService.compute_cpm_schedule(tdicts, depdicts)

    name_by_id = {t.id: t.name for t in tasks}
    task_extra = {}
    for t in tasks:
        node = result["tasks"][t.id]
        task_extra[t.id] = {
            "name": t.name,
            "progress": float(t.progress or 0),
            "status": t.status,
            "wbs_code": t.wbs_code,
            "priority": t.priority,
            "assignee_name": (t.assignee.full_name or t.assignee.username) if t.assignee else None,
            "dependency_ids": [d.predecessor_id for d in t.dependencies_from],
        }

    network = GanttAlgorithmService.generate_network_diagram_data(
        result["tasks"], result.get("dependencies", []), name_by_id, task_extra
    )
    return network


# ============== 项目级 AI 自动总结经验教训（直接入库知识库） ==============

_LESSON_CATEGORIES = ["项目管理", "技术", "沟通", "质量", "风险", "资源", "采购", "相关方"]


@router.post("/{project_id}/summarize-lessons")
async def summarize_lessons(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """触发 AI 自动总结经验教训：后台异步执行，进度经 WebSocket 实时推送，完成后广播数据变更。"""
    project = await db.get(Project, project_id)
    if not project:
        fail("项目不存在", status_code=404)
    task = AsyncTask(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        task_type="summarize_lessons",
        params={"project_id": project_id},
        status=AsyncTaskStatus.PENDING.value,
    )
    db.add(task)
    await db.commit()
    await dispatch_task(task.id)
    return {
        "success": True,
        "task_id": task.id,
        "status": "pending",
        "message": "AI 正在后台总结经验教训，完成后将实时通知",
    }



"""
顶层资源列表别名路由

为 PMBOK 业务核心资源提供顶层 `GET /xxx` 列表端点，
避免前端调用时必须先知道项目 ID 的限制。

支持：
- GET /comments              → 全部评论（可按 project_id/task_id 过滤）
- GET /budgets               → 全部预算（可按 project_id 过滤）
- GET /stakeholders          → 全部相关方（可按 project_id 过滤）
- GET /deliverables          → 全部可交付物（可按 project_id 过滤）

注意：写操作仍需 /projects/{id}/xxx 路径，确保项目归属校验。

[PMBOK KA: 整合管理 — 资源统一视图]
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User, Comment, Project
from app.models.budget import ProjectBudget, BudgetCategory
from app.models.pm_extras import ChangeRequest

router = APIRouter()


@router.get("/comments", tags=["评论"])
async def list_all_comments(
    project_id: Optional[str] = Query(None, description="按项目过滤"),
    task_id: Optional[str] = Query(None, description="按任务过滤"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出全部评论，可按项目/任务过滤。"""
    q = select(Comment).where(Comment.is_deleted == False)
    if project_id:
        q = q.where(Comment.project_id == project_id)
    if task_id:
        q = q.where(Comment.task_id == task_id)
    q = q.order_by(desc(Comment.created_at)).limit(limit)
    res = await db.execute(q)
    return {
        "items": [
            {
                "id": c.id,
                "project_id": c.project_id,
                "task_id": c.task_id,
                "content": c.content,
                "author_id": c.author_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in res.scalars().all()
        ]
    }


@router.get("/budgets", tags=["预算管理"])
async def list_all_budgets(
    project_id: Optional[str] = Query(None, description="按项目过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出全部项目预算，可按项目过滤。"""
    q = select(ProjectBudget)
    if project_id:
        q = q.where(ProjectBudget.project_id == project_id)
    q = q.order_by(desc(ProjectBudget.created_at))
    res = await db.execute(q)
    return {
        "items": [
            {
                "id": b.id,
                "project_id": b.project_id,
                "name": getattr(b, "name", None),
                "total_amount": float(b.total_amount) if getattr(b, "total_amount", None) is not None else 0,
                "status": getattr(b, "status", None),
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in res.scalars().all()
        ]
    }


@router.get("/stakeholders", tags=["相关方管理"])
async def list_all_stakeholders(
    project_id: Optional[str] = Query(None, description="按项目过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出全部相关方。

    PMI中国 AI-PM 当前用 ProjectMember 表 + User 表承担"相关方登记册"角色，
    本端点返回所有项目成员（可按 project_id 过滤），并标注角色与组织。
    """
    from app.models.permission import ProjectMember
    q = select(ProjectMember)
    if project_id:
        q = q.where(ProjectMember.project_id == project_id)
    res = await db.execute(q)
    items = []
    for m in res.scalars().all():
        u = await db.get(User, m.user_id) if m.user_id else None
        items.append({
            "id": m.id,
            "project_id": m.project_id,
            "user_id": m.user_id,
            "user_name": u.full_name if u else None,
            "user_email": u.email if u else None,
            "role": getattr(m, "role", None),
            "joined_at": m.joined_at.isoformat() if getattr(m, "joined_at", None) else None,
        })
    return {"items": items}


@router.get("/deliverables", tags=["可交付物管理"])
async def list_all_deliverables(
    project_id: Optional[str] = Query(None, description="按项目过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出全部可交付物。

    PMI中国 AI-PM 用 ChangeRequest + Task 共同承担"可交付物登记册"角色：
    - ChangeRequest：变更请求中的"交付项"字段
    - Task（type=deliverable）：标记为可交付物的任务

    本端点返回任务标记为 deliverable 的列表。
    """
    from app.models import Task
    q = select(Task)
    if project_id:
        q = q.where(Task.project_id == project_id)
    # 任务类型为 deliverable 或 milestone 的视为可交付物
    q = q.where(Task.type.in_(["deliverable", "milestone"])) if hasattr(Task, "type") else q
    q = q.order_by(desc(Task.created_at))
    res = await db.execute(q)
    return {
        "items": [
            {
                "id": t.id,
                "project_id": t.project_id,
                "name": t.name,
                "type": getattr(t, "type", None),
                "status": t.status,
                "assignee_id": t.assignee_id,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in res.scalars().all()
        ]
    }

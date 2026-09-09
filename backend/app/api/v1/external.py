"""
PMI中国AI项目管理社区 - 统一对外 API（免登录，API Key 鉴权 + 作用域限制）
外部系统（含本地 OpenClaw）凭 API Key 调用，实现无需登录本系统即可读写信息与调用 AI。

[PMBOK KA: 采购管理 (Procurement) — 对外统一API、第三方集成]
对应PMI第6版标准：外部API管理
"""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db, async_session_maker
from app.models.api_key import ApiKey, hash_api_key
from app.models import Project, Task
from app.schemas.api_key import (
    ExternalProjectCreate,
    ExternalTaskCreate,
    ExternalAssistantRequest,
)
from app.services.ai_service import ai_service
from app.services.external_api_config import is_enabled


async def _require_enabled() -> None:
    """对外 API 总闸：未开启则返回 403，由管理员在系统设置中自主开放。"""
    if not is_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="对外 API 未启用，请在「系统设置 > 外部对接」中开放端口后再调用",
        )


# 所有 /external/* 路由统一受"是否开放端口"控制
router = APIRouter(dependencies=[Depends(_require_enabled)])

SCOPE_ALL = "*"


async def _resolve_key(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
) -> ApiKey:
    raw = x_api_key
    if not raw and authorization and authorization.startswith("Bearer "):
        raw = authorization[7:].strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 API Key（请在请求头 X-API-Key 或 Authorization: Bearer 中携带）",
        )
    async with async_session_maker() as db:
        key = (
            await db.execute(
                select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw), ApiKey.is_active == True)  # noqa: E712
            )
        ).scalar_one_or_none()
        if not key:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无效的 API Key 或已禁用")
        key.last_used_at = datetime.now()
        await db.commit()
        return key


def _check_scope(key: ApiKey, scope: str) -> None:
    scopes = key.scopes or []
    if SCOPE_ALL in scopes or scope in scopes:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"API Key 缺少权限范围：{scope}",
    )


def _project_to_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "industry_type": p.industry_type,
        "project_type": p.project_type,
        "status": p.status,
        "priority": p.priority,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _task_to_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "project_id": t.project_id,
        "name": t.name,
        "description": t.description,
        "status": t.status,
        "priority": t.priority,
        "assignee_id": t.assignee_id,
        "progress": float(t.progress) if t.progress is not None else 0,
    }


@router.get("/projects")
async def list_projects(
    db: AsyncSession = Depends(get_db),
    key: ApiKey = Depends(_resolve_key),
):
    _check_scope(key, "projects:read")
    result = await db.execute(
        select(Project).where(Project.is_deleted == False).order_by(Project.created_at.desc())  # noqa: E712
    )
    return [_project_to_dict(p) for p in result.scalars().all()]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ExternalProjectCreate,
    db: AsyncSession = Depends(get_db),
    key: ApiKey = Depends(_resolve_key),
):
    _check_scope(key, "projects:write")
    proj = Project(
        owner_id=key.created_by,
        name=payload.name,
        description=payload.description,
        industry_type=payload.industry_type or "it_software",
        priority=payload.priority or 3,
        status="planning",
    )
    db.add(proj)
    await db.commit()
    await db.refresh(proj)
    return _project_to_dict(proj)


@router.get("/projects/{project_id}/tasks")
async def list_tasks(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    key: ApiKey = Depends(_resolve_key),
):
    _check_scope(key, "tasks:read")
    result = await db.execute(
        select(Task).where(Task.project_id == project_id, Task.is_deleted == False)  # noqa: E712
    )
    return [_task_to_dict(t) for t in result.scalars().all()]


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: ExternalTaskCreate,
    db: AsyncSession = Depends(get_db),
    key: ApiKey = Depends(_resolve_key),
):
    _check_scope(key, "tasks:write")
    task = Task(
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
        priority=payload.priority or 3,
        assignee_id=payload.assignee_id,
        status="todo",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _task_to_dict(task)


@router.post("/ai/assistant")
async def external_assistant(
    req: ExternalAssistantRequest,
    db: AsyncSession = Depends(get_db),
    key: ApiKey = Depends(_resolve_key),
):
    _check_scope(key, "ai:chat")
    result = await ai_service.chat(
        message=req.message, project_id=req.project_id, context=req.context
    )
    return result

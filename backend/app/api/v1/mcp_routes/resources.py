from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends
from app.core.security import get_current_active_user
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mcp_server import mcp_server, MCPResource, MCPError, MCPErrorCode
from app.db.session import async_session_maker
from app.models import Project, Task, User


resources_router = APIRouter(dependencies=[Depends(get_current_active_user)])


class MCPResourcesListRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str = ""
    method: str = "resources/list"
    params: Dict[str, Any] = Field(default_factory=dict)


class MCPResourcesReadRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str = ""
    method: str = "resources/read"
    params: Dict[str, Any]


async def resource_projects_list() -> Dict[str, Any]:
    async with async_session_maker() as db:
        projects = (await db.execute(
            select(Project).where(Project.is_deleted == False).order_by(Project.updated_at.desc())
        )).scalars().all()
        return {
            "resource_type": "projects",
            "description": "系统中的所有项目列表",
            "total": len(projects),
            "items": [
                {
                    "id": p.id,
                    "name": p.name,
                    "status": p.status,
                    "priority": p.priority,
                    "owner_id": p.owner_id,
                    "start_date": p.start_date.isoformat() if p.start_date else None,
                    "end_date": p.end_date.isoformat() if p.end_date else None,
                }
                for p in projects
            ],
        }


async def resource_tasks_list() -> Dict[str, Any]:
    async with async_session_maker() as db:
        tasks = (await db.execute(
            select(Task).where(Task.is_deleted == False).order_by(Task.created_at.desc()).limit(100)
        )).scalars().all()
        return {
            "resource_type": "tasks",
            "description": "系统中的所有任务列表",
            "total": len(tasks),
            "items": [
                {
                    "id": t.id,
                    "name": t.name,
                    "status": t.status,
                    "project_id": t.project_id,
                    "progress": float(t.progress) if t.progress else 0,
                }
                for t in tasks
            ],
        }


async def resource_team_members() -> Dict[str, Any]:
    async with async_session_maker() as db:
        users = (await db.execute(select(User).order_by(User.created_at))).scalars().all()
        return {
            "resource_type": "team_members",
            "description": "项目团队成员信息",
            "total": len(users),
            "items": [
                {
                    "id": u.id,
                    "username": getattr(u, "username", None),
                    "email": getattr(u, "email", None),
                    "full_name": getattr(u, "full_name", None),
                    "role": getattr(u, "role", None),
                }
                for u in users
            ],
        }


async def resource_project_metrics() -> Dict[str, Any]:
    async with async_session_maker() as db:
        total_projects = (await db.execute(
            select(func.count(Project.id)).where(Project.is_deleted == False)
        )).scalar() or 0
        active_projects = (await db.execute(
            select(func.count(Project.id)).where(Project.is_deleted == False, Project.status == "active")
        )).scalar() or 0
        total_tasks = (await db.execute(
            select(func.count(Task.id)).where(Task.is_deleted == False)
        )).scalar() or 0
        completed_tasks = (await db.execute(
            select(func.count(Task.id)).where(Task.is_deleted == False, Task.status == "done")
        )).scalar() or 0
        overdue_tasks = (await db.execute(
            select(func.count(Task.id)).where(
                Task.is_deleted == False, Task.status != "done", Task.planned_end < datetime.now()
            )
        )).scalar() or 0
        avg_rows = (await db.execute(
            select(func.avg(Task.progress)).where(Task.is_deleted == False)
        )).first()
        average_progress = round(float(avg_rows[0] or 0), 2)

        return {
            "resource_type": "metrics",
            "description": "项目关键绩效指标",
            "metrics": {
                "total_projects": total_projects,
                "active_projects": active_projects,
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "overdue_tasks": overdue_tasks,
                "average_progress": average_progress,
            },
        }


def register_resources():
    """注册所有MCP资源"""
    mcp_server.register_resource(MCPResource(
        uri="projects://list",
        name="项目列表",
        description="获取系统中的所有项目",
        mime_type="application/json",
        handler=resource_projects_list,
    ))

    mcp_server.register_resource(MCPResource(
        uri="tasks://list",
        name="任务列表",
        description="获取系统中的所有任务",
        mime_type="application/json",
        handler=resource_tasks_list,
    ))

    mcp_server.register_resource(MCPResource(
        uri="team://members",
        name="团队成员",
        description="获取项目团队成员信息",
        mime_type="application/json",
        handler=resource_team_members,
    ))

    mcp_server.register_resource(MCPResource(
        uri="metrics://overview",
        name="项目指标概览",
        description="获取项目关键绩效指标",
        mime_type="application/json",
        handler=resource_project_metrics,
    ))


@resources_router.post("/resources/list")
async def mcp_resources_list(request: MCPResourcesListRequest):
    try:
        resources = mcp_server.list_resources()
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "result": {"resources": resources},
        }
    except MCPError as e:
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {"code": e.code.value, "message": e.message, "data": e.data},
        }


@resources_router.post("/resources/read")
async def mcp_resources_read(request: MCPResourcesReadRequest):
    try:
        params = request.params
        uri = params.get("uri")

        if not uri:
            raise MCPError(MCPErrorCode.INVALID_PARAMS, "Resource URI is required")

        result = await mcp_server.read_resource(uri)
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "result": result,
        }
    except MCPError as e:
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {"code": e.code.value, "message": e.message, "data": e.data},
        }

import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends
from app.core.security import get_current_active_user
from pydantic import BaseModel, Field
from sqlalchemy import select, func, Integer, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mcp_server import mcp_server, MCPTool, MCPError, MCPErrorCode
from app.services.ai_service import ai_service
from app.db.session import async_session_maker
from app.models import Project, Task, User, Risk


tools_router = APIRouter(dependencies=[Depends(get_current_active_user)])


class MCPToolsListRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str = ""
    method: str = "tools/list"
    params: Dict[str, Any] = Field(default_factory=dict)


class MCPToolsCallRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str = ""
    method: str = "tools/call"
    params: Dict[str, Any]


def _parse_dt(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


async def tool_create_task(
    project_id: str,
    name: str,
    description: str = "",
    priority: int = 3,
    status: str = "todo",
    assignee_id: Optional[str] = None,
    estimated_hours: float = 0,
    planned_start: Optional[str] = None,
    planned_end: Optional[str] = None,
) -> Dict[str, Any]:
    async with async_session_maker() as db:
        project = (await db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )).scalar_one_or_none()
        if not project:
            return {"success": False, "message": f"项目不存在: {project_id}", "data": None}

        sibling_count = (await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id, Task.parent_task_id == None, Task.is_deleted == False
            )
        )).scalar() + 1

        task = Task(
            project_id=project_id,
            name=name,
            description=description,
            priority=priority,
            status=status,
            assignee_id=assignee_id,
            estimated_hours=estimated_hours,
            planned_start=_parse_dt(planned_start),
            planned_end=_parse_dt(planned_end),
            wbs_code=str(sibling_count),
            level=1,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        return {
            "success": True,
            "message": f"任务 '{name}' 创建成功",
            "data": {
                "id": task.id,
                "project_id": task.project_id,
                "name": task.name,
                "wbs_code": task.wbs_code,
                "status": task.status,
                "priority": task.priority,
                "assignee_id": task.assignee_id,
                "estimated_hours": float(task.estimated_hours) if task.estimated_hours else 0,
                "planned_start": task.planned_start.isoformat() if task.planned_start else None,
                "planned_end": task.planned_end.isoformat() if task.planned_end else None,
            },
        }


async def tool_query_tasks(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    assignee_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    async with async_session_maker() as db:
        query = select(Task).where(Task.is_deleted == False)
        if project_id:
            query = query.where(Task.project_id == project_id)
        if status:
            query = query.where(Task.status == status)
        if assignee_id:
            query = query.where(Task.assignee_id == assignee_id)
        if search:
            query = query.where(Task.name.ilike(f"%{search}%"))
        query = query.order_by(Task.sort_order, Task.created_at).limit(limit)

        tasks = (await db.execute(query)).scalars().all()
        return {
            "success": True,
            "message": "任务查询成功",
            "data": {
                "filters": {
                    "project_id": project_id,
                    "status": status,
                    "assignee_id": assignee_id,
                    "search": search,
                },
                "limit": limit,
                "total": len(tasks),
                "tasks": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "status": t.status,
                        "priority": t.priority,
                        "progress": float(t.progress) if t.progress else 0,
                        "assignee_id": t.assignee_id,
                        "wbs_code": t.wbs_code,
                        "planned_start": t.planned_start.isoformat() if t.planned_start else None,
                        "planned_end": t.planned_end.isoformat() if t.planned_end else None,
                    }
                    for t in tasks
                ],
            },
        }


async def tool_update_task(
    task_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
    progress: Optional[float] = None,
    assignee_id: Optional[str] = None,
) -> Dict[str, Any]:
    async with async_session_maker() as db:
        task = (await db.execute(
            select(Task).where(Task.id == task_id, Task.is_deleted == False)
        )).scalar_one_or_none()
        if not task:
            return {"success": False, "message": f"任务不存在: {task_id}", "data": None}

        updated = {}
        for field, value in {
            "name": name,
            "description": description,
            "status": status,
            "priority": priority,
            "progress": progress,
            "assignee_id": assignee_id,
        }.items():
            if value is not None:
                setattr(task, field, value)
                updated[field] = value

        task.updated_at = datetime.now()
        await db.commit()
        await db.refresh(task)

        return {
            "success": True,
            "message": f"任务 {task_id} 更新成功",
            "data": {
                "task_id": task.id,
                "updated_fields": updated,
            },
        }


async def tool_generate_report(
    project_id: str,
    report_type: str = "progress",
    format: str = "json",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    async with async_session_maker() as db:
        project = (await db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )).scalar_one_or_none()
        if not project:
            return {"success": False, "message": f"项目不存在: {project_id}", "data": None}

        rows = (await db.execute(
            select(
                func.count(Task.id),
                func.sum(case((Task.status == "done", 1), else_=0)),
                func.avg(Task.progress),
            ).where(Task.project_id == project_id, Task.is_deleted == False)
        )).first()

        total = rows[0] or 0
        done = rows[1] or 0
        avg_progress = float(rows[2] or 0)
        completion_rate = round(done / total, 4) if total else 0.0

        risk_count = (await db.execute(
            select(func.count(Risk.id)).where(Risk.project_id == project_id)
        )).scalar() or 0

        delayed = (await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                Task.is_deleted == False,
                Task.status != "done",
                Task.planned_end < datetime.now(),
            )
        )).scalar() or 0

        return {
            "success": True,
            "message": f"{report_type} 报告生成成功",
            "data": {
                "project_id": project_id,
                "project_name": project.name,
                "report_type": report_type,
                "format": format,
                "period": {"start": start_date, "end": end_date},
                "summary": f"项目共 {total} 个任务，已完成 {done} 个，平均进度 {avg_progress:.1f}%。",
                "metrics": {
                    "total_tasks": total,
                    "completed_tasks": done,
                    "completion_rate": completion_rate,
                    "average_progress": round(avg_progress, 2),
                    "delayed_tasks": delayed,
                    "risk_count": risk_count,
                },
            },
        }


async def tool_analyze_project(
    project_id: str,
    analysis_type: str = "comprehensive",
) -> Dict[str, Any]:
    async with async_session_maker() as db:
        project = (await db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )).scalar_one_or_none()
        if not project:
            return {"success": False, "message": f"项目不存在: {project_id}", "data": None}

        rows = (await db.execute(
            select(
                func.count(Task.id),
                func.sum(case((Task.status == "done", 1), else_=0)),
                func.avg(Task.progress),
            ).where(Task.project_id == project_id, Task.is_deleted == False)
        )).first()
        total = rows[0] or 0
        done = rows[1] or 0
        avg_progress = float(rows[2] or 0)
        completion_rate = round(done / total, 4) if total else 0.0

        risks = (await db.execute(
            select(Risk).where(Risk.project_id == project_id).order_by(Risk.risk_score.desc())
        )).scalars().all()

        health_score = round(max(0.0, min(1.0, completion_rate * 0.6 + (avg_progress / 100.0) * 0.4)), 2)

        delayed = (await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                Task.is_deleted == False,
                Task.status != "done",
                Task.planned_end < datetime.now(),
            )
        )).scalar() or 0

        return {
            "success": True,
            "message": "项目分析完成",
            "data": {
                "project_id": project_id,
                "project_name": project.name,
                "analysis_type": analysis_type,
                "health_score": health_score,
                "metrics": {
                    "total_tasks": total,
                    "completed_tasks": done,
                    "completion_rate": completion_rate,
                    "average_progress": round(avg_progress, 2),
                    "delayed_tasks": delayed,
                },
                "risks": [
                    {
                        "name": r.name,
                        "category": r.category,
                        "level": r.status,
                        "score": float(r.risk_score) if r.risk_score else None,
                        "probability": float(r.probability) if r.probability else None,
                    }
                    for r in risks
                ],
                "recommendations": [
                    "存在延期任务，建议增加资源投入或调整排期" if delayed else "项目整体进度良好，继续保持",
                    "建议关注高优先级风险的应对计划",
                ],
            },
        }


async def tool_create_project(
    name: str,
    description: str = "",
    industry_type: str = "it_software",
    priority: int = 3,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    budget: float = 0,
    owner_id: Optional[str] = None,
) -> Dict[str, Any]:
    async with async_session_maker() as db:
        if not owner_id:
            owner = (await db.execute(select(User).order_by(User.created_at))).scalars().first()
            owner_id = owner.id if owner else "00000000-0000-0000-0000-000000000000"

        project = Project(
            name=name,
            description=description,
            industry_type=industry_type,
            priority=priority,
            start_date=_parse_dt(start_date).date() if _parse_dt(start_date) else None,
            end_date=_parse_dt(end_date).date() if _parse_dt(end_date) else None,
            budget=budget,
            owner_id=owner_id,
            status="planning",
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)

        return {
            "success": True,
            "message": f"项目 '{name}' 创建成功",
            "data": {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "industry_type": project.industry_type,
                "priority": project.priority,
                "status": project.status,
                "owner_id": project.owner_id,
                "start_date": project.start_date.isoformat() if project.start_date else None,
                "end_date": project.end_date.isoformat() if project.end_date else None,
                "budget": float(project.budget) if project.budget else 0,
            },
        }


async def tool_ai_chat(
    message: str,
    project_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        result = await ai_service.chat(message, project_id, context)
        return {
            "success": True,
            "message": "AI响应成功",
            "data": result,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"AI服务错误: {str(e)}",
            "data": None,
        }


def register_tools():
    """注册所有MCP工具"""
    mcp_server.register_tool(MCPTool(
        name="create_task",
        description="创建新任务，支持指定项目、负责人、优先级等属性",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "name": {"type": "string", "description": "任务名称"},
                "description": {"type": "string", "description": "任务描述"},
                "priority": {"type": "integer", "description": "优先级 1-5", "minimum": 1, "maximum": 5},
                "status": {"type": "string", "enum": ["todo", "in_progress", "done"], "description": "任务状态"},
                "assignee_id": {"type": "string", "description": "负责人ID"},
                "estimated_hours": {"type": "number", "description": "预估工时"},
                "planned_start": {"type": "string", "description": "计划开始日期 (ISO格式)"},
                "planned_end": {"type": "string", "description": "计划结束日期 (ISO格式)"},
            },
            "required": ["project_id", "name"],
        },
        handler=tool_create_task,
    ))

    mcp_server.register_tool(MCPTool(
        name="query_tasks",
        description="查询任务列表，支持按项目、状态、负责人等条件筛选",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "status": {"type": "string", "enum": ["todo", "in_progress", "done"], "description": "任务状态"},
                "assignee_id": {"type": "string", "description": "负责人ID"},
                "search": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回数量限制", "default": 20},
            },
        },
        handler=tool_query_tasks,
    ))

    mcp_server.register_tool(MCPTool(
        name="update_task",
        description="更新任务信息，支持修改状态、进度、负责人等",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "任务ID"},
                "name": {"type": "string", "description": "任务名称"},
                "description": {"type": "string", "description": "任务描述"},
                "status": {"type": "string", "enum": ["todo", "in_progress", "done"], "description": "任务状态"},
                "priority": {"type": "integer", "description": "优先级 1-5"},
                "progress": {"type": "number", "description": "进度 0-100"},
                "assignee_id": {"type": "string", "description": "负责人ID"},
            },
            "required": ["task_id"],
        },
        handler=tool_update_task,
    ))

    mcp_server.register_tool(MCPTool(
        name="generate_report",
        description="生成项目报告，支持进度、风险、资源等多种报告类型",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "report_type": {"type": "string", "enum": ["progress", "risk", "resource", "milestone"], "description": "报告类型"},
                "format": {"type": "string", "enum": ["json", "markdown", "pdf"], "description": "输出格式"},
                "start_date": {"type": "string", "description": "开始日期"},
                "end_date": {"type": "string", "description": "结束日期"},
            },
            "required": ["project_id"],
        },
        handler=tool_generate_report,
    ))

    mcp_server.register_tool(MCPTool(
        name="analyze_project",
        description="分析项目健康状况，识别风险和提供优化建议",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "analysis_type": {"type": "string", "enum": ["comprehensive", "schedule", "risk", "resource"], "description": "分析类型"},
            },
            "required": ["project_id"],
        },
        handler=tool_analyze_project,
    ))

    mcp_server.register_tool(MCPTool(
        name="create_project",
        description="创建新项目",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "项目名称"},
                "description": {"type": "string", "description": "项目描述"},
                "industry_type": {"type": "string", "description": "行业类型"},
                "priority": {"type": "integer", "description": "优先级 1-5"},
                "start_date": {"type": "string", "description": "开始日期"},
                "end_date": {"type": "string", "description": "结束日期"},
                "budget": {"type": "number", "description": "预算"},
            },
            "required": ["name"],
        },
        handler=tool_create_project,
    ))

    mcp_server.register_tool(MCPTool(
        name="ai_chat",
        description="与AI助手对话，获取项目管理建议",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "用户消息"},
                "project_id": {"type": "string", "description": "项目ID（可选）"},
                "context": {"type": "object", "description": "额外上下文信息"},
            },
            "required": ["message"],
        },
        handler=tool_ai_chat,
    ))


@tools_router.post("/tools/list")
async def mcp_tools_list(request: MCPToolsListRequest):
    try:
        tools = mcp_server.list_tools()
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "result": {"tools": tools},
        }
    except MCPError as e:
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {"code": e.code.value, "message": e.message, "data": e.data},
        }


@tools_router.post("/tools/call")
async def mcp_tools_call(request: MCPToolsCallRequest):
    try:
        params = request.params
        name = params.get("name")
        arguments = params.get("arguments", {})

        if not name:
            raise MCPError(MCPErrorCode.INVALID_PARAMS, "Tool name is required")

        result = await mcp_server.call_tool(name, arguments)
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

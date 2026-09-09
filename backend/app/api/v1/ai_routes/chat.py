"""
PMI中国AI项目管理社区 - AI对话与分析路由
包含AI聊天、WBS生成、项目分析、风险预测

WBS 生成 / 项目分析 / 风险预测 三类大模型任务统一走「异步任务框架」：
端点仅创建 AsyncTask 并 dispatch，立即返回 task_id；
后台 handler 执行完成后经 WebSocket 实时推送进度与结果（见 app.services.async_llm_handlers）。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from typing import Dict, Any, Optional
import uuid
from datetime import datetime

from app.db.session import get_db
from app.models import Project, Task, User, Risk
from app.schemas import (
    WBSGenerationRequest,
    WBSGenerationResponse,
    AIChatRequest,
    AIChatResponse,
)
from app.core.security import get_current_user
from app.services.ai_service import ai_service
from app.api.v1.tasks import generate_wbs_code
from app.models.async_task import AsyncTask, AsyncTaskStatus
from app.services.async_task_runner import dispatch_task
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ai/generate-wbs")
async def generate_wbs(
    request: WBSGenerationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """触发 WBS 生成：后台异步执行，进度经 WebSocket 实时推送，完成后可回写为任务/风险。"""
    task = AsyncTask(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        task_type="generate_wbs",
        params={
            "project_name": request.project_name,
            "project_description": request.project_description,
            "industry_type": request.industry_type,
            "constraints": request.constraints or {},
            "project_id": request.project_id,
            "save_to_tasks": bool(request.save_to_tasks),
            "kb_id": request.kb_id,
        },
        status=AsyncTaskStatus.PENDING.value,
    )
    db.add(task)
    await db.commit()
    await dispatch_task(task.id)
    return {
        "success": True,
        "task_id": task.id,
        "status": "pending",
        "message": "AI 正在后台生成 WBS，完成后将实时通知",
    }


@router.post("/ai/chat")
async def ai_chat(
    request: AIChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        result = await ai_service.chat(
            message=request.message,
            project_id=request.project_id,
            kb_id=request.kb_id,
        )
        return AIChatResponse(**result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI chat failed: {str(e)}")


@router.post("/ai/chat/stream")
async def ai_chat_stream(
    request: AIChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    async def event_generator():
        try:
            async for chunk in ai_service.stream_chat(
                message=request.message,
                project_id=request.project_id,
                kb_id=request.kb_id,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: AI服务暂时不可用：{str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/ai/analyze-project/{project_id}")
async def analyze_project(
    project_id: str,
    kb_id: Optional[str] = Query(None, description="参照的知识库 ID（公开/本人私密二选一）。为空则默认使用公开知识库"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """触发项目 AI 分析：后台异步执行，进度经 WebSocket 实时推送。"""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    task = AsyncTask(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        task_type="analyze_project",
        params={"project_id": project_id, "kb_id": kb_id},
        status=AsyncTaskStatus.PENDING.value,
    )
    db.add(task)
    await db.commit()
    await dispatch_task(task.id)
    return {
        "success": True,
        "task_id": task.id,
        "status": "pending",
        "message": "AI 正在后台分析项目，完成后将实时通知",
    }


@router.post("/ai/predict-risk/{project_id}")
async def predict_risk(
    project_id: str,
    kb_id: Optional[str] = Query(None, description="参照的知识库 ID（公开/本人私密二选一）。为空则默认使用公开知识库"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """触发项目风险预测：后台异步执行，进度经 WebSocket 实时推送。"""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    task = AsyncTask(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        task_type="predict_risk",
        params={"project_id": project_id, "kb_id": kb_id},
        status=AsyncTaskStatus.PENDING.value,
    )
    db.add(task)
    await db.commit()
    await dispatch_task(task.id)
    return {
        "success": True,
        "task_id": task.id,
        "status": "pending",
        "message": "AI 正在后台预测风险，完成后将实时通知",
    }

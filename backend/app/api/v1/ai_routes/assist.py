"""
PMI中国AI项目管理社区 - AI 辅助填写 API
为各业务模块表单提供"AI 帮我填"能力：根据已填字段补全缺失项并优化。

该能力统一走「异步任务框架」：端点仅创建 AsyncTask 并 dispatch，立即返回 task_id；
后台 handler 完成后经 WebSocket 实时推送进度与补全结果（见 app.services.async_llm_handlers）。
"""

import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional

from app.core.security import get_current_user
from app.models import User
from app.models.async_task import AsyncTask, AsyncTaskStatus
from app.services.async_task_runner import dispatch_task

router = APIRouter()


class AssistFillRequest(BaseModel):
    form_type: str  # project / task / risk / change / approval / lesson / okr / roadmap ...
    fields: Dict[str, Any]  # 已填字段（或空）
    context: Optional[Dict[str, Any]] = None  # 补充上下文（如项目名称/描述）

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class AssistFillResponse(BaseModel):
    suggestions: Dict[str, Any] = {}
    improve_tips: list = []
    form_type: str = ""
    error: Optional[str] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


@router.post("/ai/assist-fill")
async def assist_fill(
    req: AssistFillRequest,
    current_user: User = Depends(get_current_user),
):
    """触发 AI 辅助填写：后台异步执行，进度与结果经 WebSocket 实时推送。"""
    task = AsyncTask(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        task_type="assist_fill",
        params={
            "form_type": req.form_type,
            "fields": req.fields,
            "context": req.context or {},
        },
        status=AsyncTaskStatus.PENDING.value,
    )
    from app.db.session import async_session_maker
    async with async_session_maker() as db:
        db.add(task)
        await db.commit()
        await db.refresh(task)
        await dispatch_task(task.id)
    return {
        "success": True,
        "task_id": task.id,
        "status": "pending",
        "message": "AI 正在补全并优化表单字段，完成后将实时通知",
    }

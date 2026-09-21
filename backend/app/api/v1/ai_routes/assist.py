"""
PMI中国AI项目管理社区 - AI 辅助填写 API
为各业务模块表单提供"AI 帮我填"能力：根据已填字段补全缺失项并优化。

该能力统一走「异步任务框架」：端点仅创建 AsyncTask 并 dispatch，立即返回 task_id；
后台 handler 完成后经 WebSocket 实时推送进度与补全结果（见 app.services.async_llm_handlers）。
"""

import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional

from app.core.security import get_current_user
from app.models import User
from app.models.async_task import AsyncTask, AsyncTaskStatus
from app.services.async_task_runner import dispatch_task

logger = logging.getLogger(__name__)

router = APIRouter()


class AssistFillRequest(BaseModel):
    form_type: str  # project / task / risk / change / approval / lesson / okr / roadmap ...
    fields: Dict[str, Any]  # 已填字段（或空）
    context: Optional[Dict[str, Any]] = None  # 补充上下文（如项目名称/描述）
    # 运行时枚举取值，形如 {"project_type": ["it_software", "construction"]}。
    # 由前端把下拉框的合法选项传进来，使模型只在合法取值内选择（提升准确率）。
    options: Optional[Dict[str, Any]] = None

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
    """触发 AI 辅助填写。

    返回分两段（2026-09-19 起）：

    - `instant`：**规则层结果，0ms 可得**。日期跨度、预估工时、状态/优先级默认值等
      「按规则就能定」的字段，前端收到即可立刻回填，不必盯着空表单等模型。
      这是把 2~9 秒的上游排队延迟"藏起来"的主要手段。
    - `task_id`：模型层结果，后台异步执行，完成后经 WebSocket 推送。

    若请求里连"可依据的信号"都没有（表单为空、且没选项目），
    则**不建任务、不调模型**，直接返回 `need_input` 与可操作提示 ——
    本项目网关一次调用要等 2~9 秒，花这么久换一句"我编不出来"是最差的体验。
    """
    from app.services.ai import context_builder as cb
    from app.services.ai import form_specs as fs

    form_type = (req.form_type or "task").strip().lower()
    fields = req.fields or {}
    context = req.context or {}

    instant = fs.deterministic_suggestions(form_type, fields)

    # 已登记的表单类型才做"依据不足"拦截；未登记的走宽松模式，不拦
    if fs.get_form_spec(form_type) and not cb.has_cheap_signal(form_type, fields, context):
        logger.info(
            "assist-fill 依据不足，未建任务 form_type=%s fields=%s",
            form_type, sorted(fields.keys()),
        )
        return {
            "success": False,
            "need_input": True,
            "instant": instant,
            "message": cb.NO_SIGNAL_MESSAGE,
        }

    task = AsyncTask(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        task_type="assist_fill",
        params={
            "form_type": form_type,
            "fields": fields,
            "context": context,
            "options": req.options or {},
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
        "instant": instant,
        "message": "AI 正在补全并优化表单字段，完成后将实时通知",
    }

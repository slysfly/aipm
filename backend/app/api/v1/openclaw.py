"""
PMI中国AI项目管理社区 - OpenClaw 集成路由
- /openclaw/assistant/chat：全局 AI 对话助手（使用本系统配置的大模型，与 OpenClaw 模型保持一致）
- /openclaw/status：OpenClaw 接入状态
外部系统（含本地 OpenClaw）可凭 API Key 调用 /api/v1/external/* 实现免登录对接。

[PMBOK KA: 采购管理 (Procurement) — OpenClaw外部平台集成]
对应PMI第6版标准：外部集成
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.security import get_current_user, ensure_project_access
from app.db.session import get_db
from app.models import User
from app.services.ai_service import ai_service
from app.services.openclaw_service import get_openclaw_config

router = APIRouter()


class AssistantChatRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    project_id: Optional[str] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class AssistantChatResponse(BaseModel):
    message: str
    confidence: float = 0.9
    actions: List[Any] = []
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ActionExecuteRequest(BaseModel):
    project_id: str
    client_token: str            # 前端每张操作卡片一个 UUID（幂等键）
    actions: List[Dict[str, Any]]

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ActionExecuteResponse(BaseModel):
    success: bool
    results: List[Dict[str, Any]]
    succeeded: int
    failed: int
    truncated: bool = False

    model_config = {"from_attributes": True, "protected_namespaces": ()}


@router.post("/assistant/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    req: AssistantChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 对象级鉴权：指定 project_id 时校验成员关系，防止跨项目 AI 上下文越权访问
    if req.project_id:
        await ensure_project_access(db, current_user, req.project_id)
    result = await ai_service.chat(
        message=req.message, project_id=req.project_id, context=req.context
    )
    return AssistantChatResponse(
        message=result.get("message", ""),
        confidence=result.get("confidence", 0.9),
        actions=result.get("actions", []),
    )


@router.get("/status")
async def openclaw_status(_: User = Depends(get_current_user)):
    cfg = await get_openclaw_config()
    return {
        "openclaw_enabled": cfg.enabled,
        "openclaw_base_url": cfg.base_url,
        "note": "本系统大模型配置变更后会自动同步到本地 OpenClaw（~/.openclaw/system_model.json）。",
    }


@router.post("/assistant/actions/execute", response_model=ActionExecuteResponse)
async def execute_actions(
    req: ActionExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """执行 AI 建议的操作（建任务 / 改任务状态等），真实写入数据库。

    - 对象级鉴权：execute 必须带上属于当前用户的 project_id（确保_project_access）。
    - 幂等：client_token 唯一索引，同一卡片重复确认只执行一次。
    - 跨项目越权：update_task_status 的目标任务若不属于该项目，该条记 AUTH_DENIED 并跳过。
    """
    if req.project_id:
        await ensure_project_access(db, current_user, req.project_id)
    if not req.client_token or not req.client_token.strip():
        raise HTTPException(status_code=400, detail="client_token 不能为空（前端每张操作卡片必须携带唯一 UUID）")
    if not req.actions:
        raise HTTPException(status_code=400, detail="actions 不能为空")
    from app.services.ai_action_service import ai_action_service

    try:
        res = await ai_action_service.execute_actions(
            db,
            user=current_user,
            project_id=req.project_id,
            client_token=req.client_token,
            actions=req.actions,
        )
    except IntegrityError:
        # 并发重复确认兜底：另一请求已落库，本会话已在服务层回滚（含可能重复的建库）。
        # 直接返回幂等成功，避免 500；真实数据由胜者请求写入。
        return ActionExecuteResponse(
            success=True,
            results=[],
            succeeded=0,
            failed=0,
            truncated=False,
        )
    return ActionExecuteResponse(
        success=res["failed"] == 0,
        results=res["results"],
        succeeded=res["succeeded"],
        failed=res["failed"],
        truncated=res.get("truncated", False),
    )

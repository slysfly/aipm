"""
PMI中国AI项目管理社区 - OpenClaw 集成路由
- /openclaw/assistant/chat：全局 AI 对话助手（使用本系统配置的大模型，与 OpenClaw 模型保持一致）
- /openclaw/status：OpenClaw 接入状态
外部系统（含本地 OpenClaw）可凭 API Key 调用 /api/v1/external/* 实现免登录对接。

[PMBOK KA: 采购管理 (Procurement) — OpenClaw外部平台集成]
对应PMI第6版标准：外部集成
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession

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
    )


@router.get("/status")
async def openclaw_status(_: User = Depends(get_current_user)):
    cfg = await get_openclaw_config()
    return {
        "openclaw_enabled": cfg.enabled,
        "openclaw_base_url": cfg.base_url,
        "note": "本系统大模型配置变更后会自动同步到本地 OpenClaw（~/.openclaw/system_model.json）。",
    }

"""
通维AI项目管理系统 - AI 辅助填写 API
为各业务模块表单提供“AI 帮我填”能力：根据已填字段补全缺失项并优化。

[PMBOK KA: 跨领域 (Cross-area) — AI辅助填写、智能提示]
对应PMI第6版标准：AI辅助填写、智能提示

[CPMAI Phase: CPMAI Phase: Business Understanding | Domain: AI Fundamentals — AI辅助业务填写]"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional

from app.core.security import get_current_user
from app.models import User
from app.services.ai_service import ai_service

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


@router.post("/assist-fill", response_model=AssistFillResponse)
async def assist_fill(
    req: AssistFillRequest,
    _: User = Depends(get_current_user),
):
    result = await ai_service.assist_fill(
        form_type=req.form_type, fields=req.fields, context=req.context
    )
    return AssistFillResponse(**result)

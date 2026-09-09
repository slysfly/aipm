"""
通维AI项目管理系统 - AI Agent API路由
支持自然语言指令执行和多轮对话

[PMBOK KA: 跨领域 | PG: 执行 (Cross-area/Executing) — AI Agent执行引擎]
对应PMI第6版标准：AI Agent执行引擎

[CPMAI Phase: CPMAI Phase: Model Development/Operationalization | Domain: AI Management — AI Agent执行引擎]
PMBOK 7th Principle: Team/Adaptability | Domain: Team — AI团队协作、适应性与韧性
PMBOK 8th: Autonomous AI Execution"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import User, AgentSession
from app.schemas import SuccessResponse
from app.core.security import get_current_user
from app.services.ai.agent_engine import agent_engine
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/agent/execute")
async def agent_execute(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """执行自然语言指令
    请求: {text, project_id, context}
    响应: {success, action_type, executed_steps, result, message}
    """
    text = request.get("text", "").strip()
    project_id = request.get("project_id")
    context = request.get("context", {})
    session_id = request.get("session_id")

    if not text:
        raise HTTPException(status_code=400, detail="指令内容不能为空")

    try:
        result = await agent_engine.execute_natural_language(
            db=db,
            user_id=current_user.id,
            project_id=project_id,
            text=text,
            context=context,
        )

        # 如果有session_id，保存对话记录
        if session_id:
            session_result = await db.execute(
                select(AgentSession).where(
                    AgentSession.id == session_id,
                    AgentSession.user_id == current_user.id
                )
            )
            session = session_result.scalar_one_or_none()
            if session:
                messages = session.messages or []
                messages.append({
                    "role": "user",
                    "content": text,
                    "timestamp": datetime.now().isoformat(),
                })
                messages.append({
                    "role": "assistant",
                    "content": result.get("message", ""),
                    "timestamp": datetime.now().isoformat(),
                    "action_type": result.get("action_type"),
                    "executed_steps": result.get("executed_steps"),
                    "result": result.get("result"),
                })
                session.messages = messages
                session.updated_at = datetime.now()
                await db.commit()

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent执行失败: {str(e)}")


@router.post("/agent/chat")
async def agent_chat_stream(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Agent对话模式（支持多轮，SSE流式返回）
    请求: {message, session_id, project_id}
    """
    message = request.get("message", "").strip()
    session_id = request.get("session_id")
    project_id = request.get("project_id")

    if not message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    # 获取或创建会话历史
    history_messages = []
    if session_id:
        session_result = await db.execute(
            select(AgentSession).where(
                AgentSession.id == session_id,
                AgentSession.user_id == current_user.id
            )
        )
        session = session_result.scalar_one_or_none()
        if session and session.messages:
            for msg in session.messages[-10:]:  # 最近10条
                if msg.get("role") in ["user", "assistant"]:
                    history_messages.append({
                        "role": msg["role"],
                        "content": msg.get("content", ""),
                    })

    # 添加当前消息
    all_messages = history_messages + [{"role": "user", "content": message}]

    async def event_generator():
        full_content = ""
        try:
            async for chunk in agent_engine.chat_stream(
                messages=all_messages,
                project_id=project_id,
            ):
                full_content += chunk
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: Agent服务暂时不可用：{str(e)}\n\n"
            yield "data: [DONE]\n\n"

        # 保存对话记录
        if session_id:
            try:
                session_result = await db.execute(
                    select(AgentSession).where(
                        AgentSession.id == session_id,
                        AgentSession.user_id == current_user.id
                    )
                )
                session = session_result.scalar_one_or_none()
                if session:
                    messages = session.messages or []
                    messages.append({
                        "role": "user",
                        "content": message,
                        "timestamp": datetime.now().isoformat(),
                    })
                    messages.append({
                        "role": "assistant",
                        "content": full_content,
                        "timestamp": datetime.now().isoformat(),
                    })
                    session.messages = messages
                    session.updated_at = datetime.now()
                    await db.commit()
            except Exception as e:
                logger.warning("保存 Agent 会话消息失败（已忽略）: %s", e, exc_info=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/agent/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {
        "session_id": session.id,
        "title": session.title,
        "project_id": session.project_id,
        "messages": session.messages or [],
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


@router.post("/agent/sessions", status_code=201)
async def create_session(
    request: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    title = request.get("title", "新对话")
    project_id = request.get("project_id")

    session = AgentSession(
        user_id=current_user.id,
        project_id=project_id,
        title=title,
        messages=[],
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "session_id": session.id,
        "title": session.title,
        "project_id": session.project_id,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.get("/agent/sessions")
async def list_sessions(
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(AgentSession).where(AgentSession.user_id == current_user.id)
    if project_id:
        query = query.where(AgentSession.project_id == project_id)

    query = query.order_by(AgentSession.updated_at.desc())
    result = await db.execute(query)
    sessions = result.scalars().all()

    return {
        "items": [
            {
                "id": s.id,
                "title": s.title,
                "project_id": s.project_id,
                "message_count": len(s.messages) if s.messages else 0,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ]
    }


@router.delete("/agent/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    await db.delete(session)
    await db.commit()

    return SuccessResponse(message="会话删除成功")

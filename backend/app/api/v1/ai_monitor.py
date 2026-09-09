"""
通维AI项目管理系统 - AI监控仪表盘路由（只读）

提供 LLM 调用统计和 Agent 运行监控指标。
数据来源：AgentSession 表（记录所有 Agent 执行日志）

[PMBOK KA: 跨领域 | PG: 监控 (Monitoring & Controlling) — AI监控仪表盘]
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc, cast, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import AgentSession, User
from app.models.system_llm_config import SystemLLMConfig
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


async def _parse_agent_type(title: str) -> str:
    """从 AgentSession.title 中解析 agent_type，如 '[evm] xxx' -> 'evm'"""
    if title and title.startswith("["):
        end = title.find("]")
        if end > 0:
            return title[1:end]
    return "unknown"


@router.get("/ai/monitor/stats")
async def get_ai_monitor_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """返回 AI / LLM 调用聚合统计"""
    # 1. 总调用次数（AgentSession 记录数）
    total_calls_result = await db.execute(select(func.count(AgentSession.id)))
    total_calls = total_calls_result.scalar() or 0

    # 2. 按 agent_type 统计
    all_sessions = (await db.execute(
        select(AgentSession).order_by(desc(AgentSession.created_at))
    )).scalars().all()

    calls_by_agent: Dict[str, int] = {}
    calls_by_provider: Dict[str, int] = {}
    total_tokens_est = 0
    total_latency_ms = 0.0
    success_count = 0
    error_count = 0
    recent_errors: List[Dict[str, Any]] = []

    for s in all_sessions:
        agent_type = await _parse_agent_type(s.title)
        calls_by_agent[agent_type] = calls_by_agent.get(agent_type, 0) + 1

        # 分析 messages 中的执行结果
        msgs = s.messages or []
        has_error = False
        for msg in msgs:
            if isinstance(msg, dict):
                # 简单错误检测
                content = str(msg.get("content", ""))
                if "error" in content.lower() or "exception" in content.lower() or "失败" in content:
                    has_error = True

                result_summary = str(msg.get("result_summary", ""))
                if "error" in result_summary.lower() or "exception" in result_summary.lower():
                    has_error = True

        if has_error:
            error_count += 1
            if len(recent_errors) < 20:
                recent_errors.append({
                    "agent_type": agent_type,
                    "title": s.title,
                    "time": s.created_at.isoformat() if s.created_at else None,
                    "session_id": s.id,
                })
        else:
            success_count += 1

        # 估算 token 用量（基于消息长度），后续可替换为真实 token 计数器
        for msg in msgs:
            if isinstance(msg, dict):
                content_len = len(str(msg.get("content", "")))
                total_tokens_est += content_len // 2  # 粗略估计

    # 处理 Provider 映射
    # 当前系统主要使用 minimax / openai，从 AgentSession 无法直接获取 provider
    # 从 SystemLLMConfig 获取配置信息
    provider_configs = (await db.execute(
        select(SystemLLMConfig)
    )).scalars().all()

    for cfg in provider_configs:
        provider_name = cfg.provider_name or "unknown"
        if provider_name not in calls_by_provider:
            calls_by_provider[provider_name] = 0
    # 如果有配置但没有调用，设置默认值
    if calls_by_provider and not any(v > 0 for v in calls_by_provider.values()):
        for k in calls_by_provider:
            calls_by_provider[k] = total_calls // max(len(calls_by_provider), 1)
    elif not calls_by_provider:
        calls_by_provider["minimax"] = total_calls
        calls_by_provider["openai"] = 0

    # 计算统计指标
    avg_latency_ms = round(total_latency_ms / max(total_calls, 1), 1)
    success_rate = round(success_count / max(total_calls, 1), 4)

    # 最近7天数据
    seven_days_ago = datetime.now() - timedelta(days=7)
    recent_count_result = await db.execute(
        select(func.count(AgentSession.id)).where(
            AgentSession.created_at >= seven_days_ago
        )
    )
    recent_calls = recent_count_result.scalar() or 0

    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens_est,
        "avg_latency_ms": avg_latency_ms,
        "success_rate": success_rate,
        "calls_by_provider": calls_by_provider,
        "calls_by_agent": calls_by_agent,
        "recent_errors": recent_errors,
        "recent_calls_7d": recent_calls,
    }


@router.get("/ai/monitor/calls")
async def get_ai_monitor_calls(
    provider: Optional[str] = Query(None, description="按 provider 过滤"),
    agent_type: Optional[str] = Query(None, description="按 agent_type 过滤"),
    status: Optional[str] = Query(None, description="状态过滤: success/error"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """分页返回详细 AI 调用记录"""
    query = select(AgentSession)

    if agent_type:
        query = query.where(AgentSession.title.like(f"[{agent_type}]%"))

    # 获取总数
    count_query = select(func.count(AgentSession.id))
    if agent_type:
        count_query = count_query.where(AgentSession.title.like(f"[{agent_type}]%"))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页 + 排序
    query = query.order_by(desc(AgentSession.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(query)).scalars().all()

    items = []
    for s in rows:
        atype = await _parse_agent_type(s.title or "")
        msgs = s.messages or []

        # 分析状态
        has_error = False
        result_summary = ""
        for msg in msgs:
            if isinstance(msg, dict):
                content = str(msg.get("content", ""))
                if "error" in content.lower() or "exception" in content.lower() or "失败" in content:
                    has_error = True
                summary = msg.get("result_summary", "")
                if summary:
                    result_summary = summary

        call_status = "error" if has_error else "success"

        # 如果按 status 过滤
        if status and call_status != status:
            continue

        items.append({
            "id": s.id,
            "agent_type": atype,
            "title": s.title,
            "summary": result_summary,
            "status": call_status,
            "project_id": s.project_id,
            "user_id": s.user_id,
            "message_count": len(msgs),
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }

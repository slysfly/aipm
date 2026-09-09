"""
PMI中国AI项目管理社区 - LLM 调用度量与埋点

在 AIEngine 统一调用入口处记录每次 LLM 调用的真实可观测指标：
- Token 用量（基于字符的混合估算，对中英文均较准确）
- 端到端延迟
- 参考成本（美元，按各厂商公开定价）
- 状态（成功/失败）

通过 contextvars 携带 user/project/agent 上下文，由调用方（Agent 引擎等）设置。
落库为 best-effort：任何异常都被吞掉，绝不阻塞 LLM 主流程。

[PMBOK KA: 跨领域 | PG: 监控 — AI成本绩效度量]
"""

import asyncio
import logging
import time
from contextvars import ContextVar
from typing import Any, Dict, Optional

from app.db.session import async_session_maker
from app.models import LLMCallLog

logger = logging.getLogger(__name__)

# 调用上下文：调用方（如 Agent 引擎）通过 set_llm_context 注入
_llm_ctx: ContextVar[Dict[str, Any]] = ContextVar("llm_ctx", default={})

# ---------------------------------------------------------------------------
# Token 估算（中英文混合）
# 经验值：中文 ~1.5 字符/token，英文/符号 ~4 字符/token
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """估算文本 token 数（中英文混合）"""
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        if "一" <= ch <= "鿿" or "぀" <= ch <= "ヿ" or "⺀" <= ch <= "䶿":
            cjk += 1
        else:
            other += 1
    return int(cjk * 1.5 + other / 4) + 1


# ---------------------------------------------------------------------------
# 参考定价（美元 / 每 1M tokens）— 公开价格近似值，仅用于成本可视化
# key: provider -> {model_substring: (input_per_M, output_per_M)}
# ---------------------------------------------------------------------------

PRICING: Dict[str, Dict[str, tuple]] = {
    "openai": {
        "gpt-4o": (2.5, 10.0),
        "gpt-4o-mini": (0.15, 0.6),
        "gpt-4-turbo": (10.0, 30.0),
        "gpt-3.5-turbo": (0.5, 1.5),
        "o1": (15.0, 60.0),
        "default": (2.5, 10.0),
    },
    "deepseek": {
        "deepseek-chat": (0.27, 1.1),
        "deepseek-reasoner": (0.55, 2.19),
        "default": (0.27, 1.1),
    },
    "anthropic": {
        "claude-3-5-sonnet": (3.0, 15.0),
        "claude-3-opus": (15.0, 75.0),
        "claude-3-haiku": (0.25, 1.25),
        "default": (3.0, 15.0),
    },
    "minimax": {"default": (1.0, 3.0)},
    "qwen": {"default": (0.4, 1.2)},
    "moonshot": {"default": (1.0, 1.0)},
    "zhipu": {"default": (1.0, 1.0)},
    "baidu": {"default": (0.8, 0.8)},
    "aliyun": {"default": (0.4, 1.2)},
    "tencent": {"default": (0.8, 0.8)},
    "siliconflow": {"default": (0.3, 0.6)},
    "openai_compatible": {"default": (1.0, 2.0)},
}


def estimate_cost(provider: str, model: str, prompt_tok: int, completion_tok: int) -> float:
    """估算一次调用的参考成本（美元）"""
    prov = PRICING.get(provider, {})
    rates = None
    if prov:
        for key, val in prov.items():
            if key != "default" and key and key in (model or ""):
                rates = val
                break
        if rates is None:
            rates = prov.get("default", (1.0, 2.0))
    else:
        rates = (1.0, 2.0)
    in_rate, out_rate = rates
    return round((prompt_tok * in_rate + completion_tok * out_rate) / 1_000_000, 6)


# ---------------------------------------------------------------------------
# 上下文注入
# ---------------------------------------------------------------------------

def set_llm_context(**kwargs) -> None:
    """设置当前调用上下文（user_id / project_id / task_name）"""
    ctx = _llm_ctx.get()
    ctx = {**ctx, **kwargs}
    _llm_ctx.set(ctx)


def get_llm_context() -> Dict[str, Any]:
    return _llm_ctx.get()


# ---------------------------------------------------------------------------
# 落库（best-effort）
# ---------------------------------------------------------------------------

async def record_llm_call(
    provider: str,
    model: str,
    prompt_text: str,
    completion_text: str,
    latency_ms: int,
    status: str = "success",
    error_message: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    异步记录一次 LLM 调用。任何异常都被吞掉，绝不阻塞主流程。
    """
    try:
        ctx = get_llm_context()
        if extra:
            ctx = {**ctx, **extra}

        prompt_tok = estimate_tokens(prompt_text)
        completion_tok = estimate_tokens(completion_text)
        total_tok = prompt_tok + completion_tok
        cost = estimate_cost(provider, model, prompt_tok, completion_tok)

        log = LLMCallLog(
            provider=provider,
            model=model,
            task_name=ctx.get("task_name"),
            user_id=ctx.get("user_id"),
            project_id=ctx.get("project_id"),
            prompt_tokens=prompt_tok,
            completion_tokens=completion_tok,
            total_tokens=total_tok,
            latency_ms=latency_ms,
            cost_usd=cost,
            status=status,
            error_message=(error_message or "")[:2000] if error_message else None,
        )

        async with async_session_maker() as session:
            session.add(log)
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug("LLM 调用埋点写入失败（已忽略）: %s", e)


def record_llm_call_sync(*args, **kwargs) -> None:
    """在同步上下文中触发异步落库（fire-and-forget）"""
    try:
        asyncio.create_task(record_llm_call(*args, **kwargs))
    except RuntimeError:
        # 无运行中的事件循环（如测试/脚本），降级为内联协程
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(record_llm_call(*args, **kwargs))
            loop.close()
        except Exception:  # noqa: BLE001
            pass

"""
LLM 监控面板（#3）端到端测试

覆盖：
1. /ai/monitor/stats  — 含真实度量字段
2. /ai/monitor/usage  — 按模型聚合（含直接落库后的聚合校验）
3. /ai/monitor/usage/trend — 趋势
4. /ai/monitor/ab-test — 模型 A/B 对比
5. metrics.estimate_tokens / estimate_cost 纯函数
"""

import pytest

from app.core.ai_engine.metrics import estimate_tokens, estimate_cost
from app.db.session import async_session_maker
from app.models import LLMCallLog


# =========================================================================== #
# 纯函数单测
# =========================================================================== #

def test_estimate_tokens_empty():
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0


def test_estimate_tokens_english():
    # 英文约 4 字符/token
    n = estimate_tokens("hello world this is a test")
    assert 4 <= n <= 8


def test_estimate_tokens_chinese():
    # 中文约 1.5 字符/token
    n = estimate_tokens("人工智能项目管理平台")
    assert n >= 9  # 11 字 * 1.5 ≈ 16


def test_estimate_cost_known_provider():
    c = estimate_cost("openai", "gpt-4o", 1000, 500)
    assert c > 0
    # gpt-4o: 2.5/1M in, 10/1M out -> (1000*2.5 + 500*10)/1e6 = 0.0075
    assert abs(c - 0.0075) < 1e-4


def test_estimate_cost_unknown_provider_fallback():
    c = estimate_cost("no_such_provider", "model-x", 1000, 500)
    assert c >= 0


# =========================================================================== #
# 接口测试
# =========================================================================== #

async def test_monitor_stats_schema(client, auth_headers):
    r = await client.get("/api/v1/ai/monitor/stats", headers=auth_headers)
    assert r.status_code == 200
    b = r.json()
    for key in (
        "total_calls", "recent_calls_7d",
        "real_total_calls", "real_total_tokens",
        "real_total_cost_usd", "real_avg_latency_ms", "real_success_rate",
    ):
        assert key in b, f"stats 缺少字段 {key}"


async def test_monitor_usage_empty(client, auth_headers):
    r = await client.get("/api/v1/ai/monitor/usage", headers=auth_headers)
    assert r.status_code == 200
    b = r.json()
    assert "items" in b
    assert "summary" in b
    assert b["summary"]["total_calls"] == 0


async def test_monitor_usage_trend_empty(client, auth_headers):
    r = await client.get("/api/v1/ai/monitor/usage/trend", params={"days": 7}, headers=auth_headers)
    assert r.status_code == 200
    assert "trend" in r.json()
    assert "days" in r.json()


async def test_monitor_ab_test(client, auth_headers):
    r = await client.get(
        "/api/v1/ai/monitor/ab-test",
        params={"model_a": "openai/gpt-4o", "model_b": "deepseek/deepseek-chat"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    b = r.json()
    assert b["model_a"] == "openai/gpt-4o"
    assert b["model_b"] == "deepseek/deepseek-chat"
    assert "a" in b and "b" in b


async def test_monitor_usage_aggregation_after_insert(client, auth_headers):
    """直接落库一条 LLMCallLog，验证 usage 聚合能统计到它"""
    async with async_session_maker() as session:
        session.add(LLMCallLog(
            provider="openai",
            model="gpt-4o",
            task_name="wbs",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            latency_ms=820,
            cost_usd=0.0075,
            status="success",
        ))
        await session.commit()

    r = await client.get("/api/v1/ai/monitor/usage", headers=auth_headers)
    assert r.status_code == 200
    b = r.json()
    items = b["items"]
    match = [i for i in items if i["provider"] == "openai" and i["model"] == "gpt-4o"]
    assert len(match) == 1, "聚合未统计到插入的 LLMCallLog"
    row = match[0]
    assert row["calls"] >= 1
    assert row["total_tokens"] >= 1500
    assert row["total_cost_usd"] > 0
    assert row["success_rate"] >= 0.99
    assert b["summary"]["total_calls"] >= 1

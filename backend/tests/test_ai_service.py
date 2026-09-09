"""
AI 服务层测试
覆盖：AI 端点可用性、降级模式、与系统 LLM 配置的联动。
"""
import pytest


async def test_ai_endpoint_requires_auth(client):
    """AI 端点需要认证。"""
    r = await client.post("/api/v1/ai/chat", json={"message": "hello"})
    assert r.status_code == 401


async def test_ai_chat_graceful_degradation(client, auth_headers):
    """配置未完善时 AI 对话应优雅降级（返回 503 而非 500）。"""
    r = await client.post("/api/v1/ai/chat", json={"message": "你好"}, headers=auth_headers)
    # 未配置 AI Key 时系统应返回 503 Service Unavailable 而非 Crash
    assert r.status_code in (200, 503, 422), f"期望优雅降级，得到 {r.status_code}"


async def test_openclaw_sync_endpoint(client, auth_headers):
    """同步到 OpenClaw 端点需要超级用户权限。"""
    # 普通用户 (auth_headers 来自 conftest，非 superuser)
    r = await client.post("/api/v1/system/llm-config/sync-openclaw", json={}, headers=auth_headers)
    assert r.status_code == 403, f"非管理员同步应被拒绝：{r.status_code}"


async def test_list_providers_requires_admin(client, auth_headers):
    """AI 厂商列表需要超级用户。"""
    r = await client.get("/api/v1/system/llm-config/providers", headers=auth_headers)
    assert r.status_code == 403, f"非管理员应被拒绝：{r.status_code}"

"""
OpenClaw 配置持久化测试
覆盖：配置的 CRUD 与持久化确认（非全局变量）。
"""
import pytest

from conftest import _create_superuser_headers, data_of


async def test_permissions_openclaw_config_requires_admin(client, auth_headers):
    """确认非超级用户无法访问 OpenClaw 配置（无需 admin fixture，默认注册用户非 superuser）。"""
    r = await client.get("/api/v1/system/openclaw-config", headers=auth_headers)
    assert r.status_code == 403, f"非管理员应被拒绝，返回 {r.status_code}"


async def test_openclaw_config_get_default(client):
    """确认 OpenClaw 配置有合理的默认值（首次访问自动创建）。"""
    admin_headers = await _create_superuser_headers(client)
    r = await client.get("/api/v1/system/openclaw-config", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = data_of(r)
    assert body["base_url"] in ("http://localhost:18888",), f"期望默认 18888，得到 {body['base_url']}"
    assert body["enabled"] is True


async def test_openclaw_config_update(client):
    """确认更新 OpenClaw 配置后持久化生效。"""
    admin_headers = await _create_superuser_headers(client)
    r = await client.put("/api/v1/system/openclaw-config", json={
        "base_url": "http://openclaw.lan:8080",
        "enabled": False,
    }, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = data_of(r)
    assert body["base_url"] == "http://openclaw.lan:8080"
    assert body["enabled"] is False

    # 再次读取确认持久化
    r = await client.get("/api/v1/system/openclaw-config", headers=admin_headers)
    assert r.status_code == 200
    body = data_of(r)
    assert body["base_url"] == "http://openclaw.lan:8080"
    assert body["enabled"] is False

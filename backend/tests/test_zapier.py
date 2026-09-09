"""Zapier 集成测试（不触发签名校验的部分）"""
import pytest


async def test_ping(client, auth_headers):
    r = await client.get("/api/v1/zapier/ping", headers=auth_headers)
    assert r.status_code == 200

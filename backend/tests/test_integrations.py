"""集成列表相关测试（不依赖外部 OAuth 配置）"""
import pytest


async def test_list_integrations(client, auth_headers):
    r = await client.get("/api/v1/integrations", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    # 返回结构应为字典（包含提供方信息）或列表
    assert isinstance(body, (dict, list))

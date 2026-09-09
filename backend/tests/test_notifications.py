"""通知相关测试"""
import pytest


async def test_list_notifications(client, auth_headers):
    r = await client.get("/api/v1/notifications", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body or isinstance(body, dict) or isinstance(body, list)


async def test_unread_count(client, auth_headers):
    r = await client.get("/api/v1/notifications/unread-count", headers=auth_headers)
    assert r.status_code == 200


async def test_read_all(client, auth_headers):
    r = await client.put("/api/v1/notifications/read-all", headers=auth_headers)
    assert r.status_code == 200

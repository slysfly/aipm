"""报表相关测试（仅读取/生成，不触发邮件发送）"""
import pytest


async def test_daily_report(client, auth_headers):
    r = await client.get("/api/v1/reports/daily", headers=auth_headers)
    assert r.status_code == 200
    assert r.json().get("success") is True


async def test_weekly_report(client, auth_headers):
    r = await client.get("/api/v1/reports/weekly", headers=auth_headers)
    assert r.status_code == 200
    assert r.json().get("success") is True

"""认证与用户相关测试"""
import pytest


async def test_register_and_login(client):
    email = "auth_test@example.com"
    username = "auth_test"
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "Pass1234!", "full_name": "Auth"},
    )
    assert r.status_code in (200, 201), r.text

    r = await client.post("/api/v1/auth/login", json={"username": username, "password": "Pass1234!"})
    assert r.status_code == 200
    body = r.json()
    data = body.get("data", body)
    assert "access_token" in data and "refresh_token" in data


async def test_login_wrong_password(client):
    # 先确保用户存在
    await client.post(
        "/api/v1/auth/register",
        json={"email": "wp@example.com", "username": "wp", "password": "Pass1234!"},
    )
    r = await client.post("/api/v1/auth/login", json={"username": "wp", "password": "wrong"})
    assert r.status_code == 401


async def test_me_requires_auth(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_me_with_token(client, auth_headers):
    r = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["username"].startswith("tester")


async def test_refresh(client, auth_headers):
    login = await client.post(
        "/api/v1/auth/login", json={"username": "tester", "password": "Test1234!"}
    )
    login_data = login.json().get("data", login.json())
    refresh = login_data["refresh_token"]
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    refresh_data = r.json().get("data", r.json())
    assert "access_token" in refresh_data

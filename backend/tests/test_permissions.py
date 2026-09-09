"""
RBAC 权限控制测试
覆盖：超级用户 vs 普通用户对不同端点的访问控制。
"""
import pytest

from conftest import _create_superuser_headers, data_of


async def _register_and_login_as(client, suffix: str, is_superuser: bool = False):
    email = f"perm_{suffix}@example.com"
    username = f"perm_{suffix}"
    await client.post("/api/v1/auth/register", json={
        "email": email, "username": username,
        "password": "Perm1234!", "full_name": f"Perm_{suffix}",
    })
    login = await client.post("/api/v1/auth/login", json={"username": username, "password": "Perm1234!"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {data_of(login)['access_token']}"}

    if is_superuser:
        # 直接从DB提升为超级用户
        from app.db.session import async_session_maker
        from app.models import User
        from sqlalchemy import select
        async with async_session_maker() as session:
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user:
                user.is_superuser = True
                await session.commit()

    return headers


async def test_normal_user_cannot_access_admin_llm_config(client):
    """普通用户无法访问 /system/llm-config（要求 superuser）。"""
    headers = await _register_and_login_as(client, "normal_llm", is_superuser=False)
    r = await client.get("/api/v1/system/llm-config", headers=headers)
    assert r.status_code == 403, f"期望 403，得到 {r.status_code}"


async def test_superuser_can_access_admin_llm_config(client):
    """超级用户可以访问 /system/llm-config。"""
    headers = await _register_and_login_as(client, "super_llm", is_superuser=True)
    r = await client.get("/api/v1/system/llm-config", headers=headers)
    # 即使没有配置，也应该是个有效响应（200 或 404 but NOT 403）
    assert r.status_code != 403, f"超级用户被拒绝：{r.text}"
    assert r.status_code in (200, 404, 422), f"意外状态码：{r.status_code}"


async def test_normal_user_cannot_access_openclaw_config(client):
    """普通用户无法访问 /system/openclaw-config。"""
    headers = await _register_and_login_as(client, "normal_oc", is_superuser=False)
    r = await client.get("/api/v1/system/openclaw-config", headers=headers)
    assert r.status_code == 403, f"期望 403，得到 {r.status_code}"


async def test_superuser_can_access_openclaw_config(client):
    """超级用户可以访问 /system/openclaw-config。"""
    headers = await _register_and_login_as(client, "super_oc", is_superuser=True)
    r = await client.get("/api/v1/system/openclaw-config", headers=headers)
    assert r.status_code == 200, f"超级用户被拒绝：{r.text}"


async def test_normal_user_can_access_own_project_crud(client):
    """普通用户可以操作 /api/v1/projects（项目 CRUD 不需要超级用户）。"""
    headers = await _register_and_login_as(client, "proj_owner", is_superuser=False)
    # 创建项目
    r = await client.post("/api/v1/projects", json={
        "name": "用户自己的项目",
        "description": "普通用户可创建项目",
    }, headers=headers)
    assert r.status_code in (200, 201), f"项目创建失败：{r.text}"
    pid = data_of(r).get("id", "") if isinstance(data_of(r), dict) else ""
    assert pid, f"未返回项目 ID：{r.text[:200]}"


async def test_unauthenticated_user_cannot_access_any_api(client):
    """未认证用户访问任何需要认证的 API 均返回 401。"""
    r = await client.get("/api/v1/system/llm-config")
    assert r.status_code == 401, f"期望 401，得到 {r.status_code}"

    r = await client.get("/api/v1/system/openclaw-config")
    assert r.status_code == 401, f"期望 401，得到 {r.status_code}"

    r = await client.get("/api/v1/projects")
    assert r.status_code == 401, f"期望 401，得到 {r.status_code}"

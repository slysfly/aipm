"""
冒烟测试 2：F-01 对象级鉴权（显式断言）

验证此前修复的对象级鉴权契约：
- 非成员用他人项目的 token 访问 -> 期望 **403**（无权）
- 访问「不存在」的项目 -> 期望 **404**（不泄露项目存在性，绝不能是 403）
- 超管可访问他人项目 -> 期望 **200**（超管放行）
- 项目 owner 隐式访问 -> 期望 **200**
- 未携带 token -> 期望 **401**
- 非成员访问他人任务 -> 期望 **403**（require_task_membership）

运行（在 backend/ 目录下）：
    ../../venv/Scripts/python -m pytest tests/test_smoke_security_f01.py -v
"""
import uuid

from sqlalchemy import select

from app.main import app  # noqa: F401
from app.db.session import async_session_maker
from app.models import User
from app.models.permission import Role, ProjectMember
from app.core.security import get_password_hash
from conftest import data_of

BASE = "/api/v1"


async def _reg_login(client, suffix: str) -> dict:
    email = f"f01_{suffix}@example.com"
    username = f"f01_{suffix}"
    await client.post(
        f"{BASE}/auth/register",
        json={"email": email, "username": username,
              "password": "F011234!", "full_name": f"F01_{suffix}"},
    )
    r = await client.post(
        f"{BASE}/auth/login",
        json={"username": username, "password": "F011234!"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {data_of(r)['access_token']}"}


async def _create_project(client, headers, name="F01项目") -> str:
    r = await client.post(
        f"{BASE}/projects", headers=headers,
        json={"name": name, "priority": 3},
    )
    assert r.status_code in (200, 201), r.text
    return data_of(r)["id"]


async def _make_superuser(client, suffix: str) -> dict:
    """直接插入 is_superuser=True 用户（注册接口服务端强制 is_superuser=False）。"""
    email = f"f01sup_{suffix}@example.com"
    username = f"f01sup_{suffix}"
    async with async_session_maker() as db:
        u = User(
            email=email, username=username,
            hashed_password=get_password_hash("F01Sup123!"),
            is_superuser=True, is_active=True, full_name=f"超管_{suffix}",
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
    r = await client.post(
        f"{BASE}/auth/login",
        json={"username": username, "password": "F01Sup123!"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {data_of(r)['access_token']}"}


async def _add_active_member(db, user_id: str, project_id: str) -> None:
    """将 user 作为活跃成员加入 project（验证 active ProjectMember 分支）。"""
    role = (await db.execute(select(Role).limit(1))).scalar_one_or_none()
    if role is None:
        role = Role(name=f"f01_role_{uuid.uuid4().hex[:8]}", permissions=[])
        db.add(role)
        await db.commit()
        await db.refresh(role)
    m = ProjectMember(
        project_id=project_id, user_id=user_id,
        role_id=role.id, is_active=True,
    )
    db.add(m)
    await db.commit()


async def test_f01_owner_implicit_access(client):
    """owner 隐式访问自己的项目 -> 200。"""
    h = await _reg_login(client, "owner")
    pid = await _create_project(client, h, "Owner项目")
    r = await client.get(f"{BASE}/projects/{pid}", headers=h)
    assert r.status_code == 200, r.text


async def test_f01_nonmember_get_others_project_returns_403(client):
    """F-01 核心：非成员访问他人项目 -> 403（无权，不泄露存在性）。"""
    h_a = await _reg_login(client, "a")
    pid = await _create_project(client, h_a, "A的项目")
    h_b = await _reg_login(client, "b")  # B 非成员
    r = await client.get(f"{BASE}/projects/{pid}", headers=h_b)
    assert r.status_code == 403, f"期望 403，得到 {r.status_code}: {r.text}"


async def test_f01_nonexistent_project_returns_404(client):
    """F-01 核心：访问不存在项目 -> 404（绝不能 403，避免泄露存在性）。"""
    h = await _reg_login(client, "ghost")
    fake_id = str(uuid.uuid4())
    r = await client.get(f"{BASE}/projects/{fake_id}", headers=h)
    assert r.status_code == 404, f"期望 404，得到 {r.status_code}: {r.text}"
    assert r.status_code != 403, "返回 403 会泄露项目存在性（F-01 违规）"


async def test_f01_superuser_can_access_others_project(client):
    """超管放行：可访问他人项目 -> 200。"""
    h_a = await _reg_login(client, "a2")
    pid = await _create_project(client, h_a, "A2的项目")
    h_sup = await _make_superuser(client, "s1")
    r = await client.get(f"{BASE}/projects/{pid}", headers=h_sup)
    assert r.status_code == 200, r.text


async def test_f01_unauthenticated_returns_401(client):
    """未携带 token -> 401。"""
    h_a = await _reg_login(client, "a3")
    pid = await _create_project(client, h_a, "A3的项目")
    # 清除登录 cookie，确保后续请求真正匿名（AsyncClient 会跨请求持久化 cookie，
    # 否则此前种下的 access_token cookie 会被自动带上，误判为已认证）。
    client.cookies.clear()
    r = await client.get(f"{BASE}/projects/{pid}")  # 无 headers
    assert r.status_code == 401, f"期望 401，得到 {r.status_code}"


async def test_f01_nonmember_get_task_returns_403(client):
    """非成员访问他人任务 -> 403（require_task_membership 按归属项目校验）。"""
    h_a = await _reg_login(client, "ta")
    pid = await _create_project(client, h_a, "TA项目")
    t = await client.post(
        f"{BASE}/tasks", headers=h_a,
        json={"project_id": pid, "name": "任务X", "status": "todo"},
    )
    assert t.status_code in (200, 201), t.text
    tid = data_of(t)["id"]

    h_b = await _reg_login(client, "tb")  # 非成员
    r = await client.get(f"{BASE}/tasks/{tid}", headers=h_b)
    assert r.status_code == 403, f"期望 403，得到 {r.status_code}: {r.text}"


async def test_f01_active_member_can_access(client):
    """active ProjectMember 分支：被显式加入后可访问 -> 200。"""
    h_a = await _reg_login(client, "ma")
    pid = await _create_project(client, h_a, "MA项目")
    h_b = await _reg_login(client, "mb")
    # 取 B 的用户 id
    me = await client.get(f"{BASE}/auth/me", headers=h_b)
    b_uid = data_of(me)["id"]

    async with async_session_maker() as db:
        await _add_active_member(db, b_uid, pid)

    r = await client.get(f"{BASE}/projects/{pid}", headers=h_b)
    assert r.status_code == 200, r.text

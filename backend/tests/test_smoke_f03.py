"""
冒烟测试 3：F-03 AI 项目隔离（显式断言）

验证此前修复：/openclaw/assistant/chat 在传 project_id 时执行成员鉴权，
确保「调用方确为该成员」，其 AI 上下文不会越权读到他人项目数据。

- 成员带「自己项目」的 project_id 对话 -> 200，且模型收到的 project_id == 自己的项目
  （证明上下文被限定在调用方所属项目，未串到他人项目）
- 非成员带「他人项目」的 project_id 对话 -> **403**，且 ai_service.chat 根本未被调用
  （证明越权 AI 上下文访问在到达模型前被拦截）
- 不带 project_id 的全局助手对话 -> 200（project_id 可选，仅在有值时校验成员）

默认用 monkeypatch + AsyncMock 桩替换 ai_service.chat 以保证确定性
（AsyncMock 非描述符，设到实例属性上不会被绑定，self 不会注入）；
设 SMOKE_LIVE_AI=1 则真实调用大模型。

运行（在 backend/ 目录下）：
    ../../venv/Scripts/python -m pytest tests/test_smoke_f03.py -v
"""
import os
import uuid
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.main import app  # noqa: F401
from app.db.session import async_session_maker
from app.models.permission import Role, ProjectMember
from conftest import data_of

BASE = "/api/v1"
_LIVE_AI = os.environ.get("SMOKE_LIVE_AI", "") in ("1", "true", "True")


async def _reg_login(client, suffix: str) -> dict:
    email = f"f03_{suffix}@example.com"
    username = f"f03_{suffix}"
    await client.post(
        f"{BASE}/auth/register",
        json={"email": email, "username": username,
              "password": "F031234!", "full_name": f"F03_{suffix}"},
    )
    r = await client.post(
        f"{BASE}/auth/login",
        json={"username": username, "password": "F031234!"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {data_of(r)['access_token']}"}


async def _create_project(client, headers, name="F03项目") -> str:
    r = await client.post(
        f"{BASE}/projects", headers=headers,
        json={"name": name, "priority": 3},
    )
    assert r.status_code in (200, 201), r.text
    return data_of(r)["id"]


async def _add_active_member(db, user_id: str, project_id: str) -> None:
    role = (await db.execute(select(Role).limit(1))).scalar_one_or_none()
    if role is None:
        role = Role(name=f"f03_role_{uuid.uuid4().hex[:8]}", permissions=[])
        db.add(role)
        await db.commit()
        await db.refresh(role)
    db.add(ProjectMember(
        project_id=project_id, user_id=user_id,
        role_id=role.id, is_active=True,
    ))
    await db.commit()


async def test_f03_member_chat_with_own_project_id(client, monkeypatch):
    """成员带自己项目的 project_id -> 200，模型收到正确的 project_id。"""
    h = await _reg_login(client, "owner")
    pid_a = await _create_project(client, h, "F03-A")

    captured = {}

    async def _side(message, project_id=None, context=None):
        captured["project_id"] = project_id
        captured["message"] = message
        return {"message": f"[stub pid={project_id}] {message}", "confidence": 0.95}

    fake = AsyncMock(side_effect=_side)
    monkeypatch.setattr("app.services.ai_service.ai_service.chat", fake)

    r = await client.post(
        f"{BASE}/openclaw/assistant/chat", headers=h,
        json={"message": "本项目进度如何", "project_id": pid_a},
    )
    assert r.status_code == 200, r.text
    assert data_of(r).get("message"), "AI 响应为空"
    assert fake.call_args is not None, "ai_service.chat 未被调用"
    assert captured.get("project_id") == pid_a, "模型收到的 project_id 不是调用方所属项目（F-03 隔离失败）"
    assert pid_a in data_of(r)["message"], "响应未携带调用方 project_id"


async def test_f03_nonmember_chat_with_others_project_id_returns_403(client, monkeypatch):
    """F-03 核心：非成员带他人 project_id -> 403，且模型根本未被调用。"""
    h_a = await _reg_login(client, "a")
    pid_a = await _create_project(client, h_a, "F03-A(他人)")
    h_b = await _reg_login(client, "b")  # B 非 A 项目成员

    fake = AsyncMock(return_value={"message": "x", "confidence": 0.9})
    monkeypatch.setattr("app.services.ai_service.ai_service.chat", fake)

    r = await client.post(
        f"{BASE}/openclaw/assistant/chat", headers=h_b,
        json={"message": "读一下那个项目", "project_id": pid_a},
    )
    assert r.status_code == 403, f"期望 403，得到 {r.status_code}: {r.text}"
    assert fake.call_args is None, "越权请求竟到达了 ai_service.chat（F-03 拦截失败）"


async def test_f03_chat_without_project_id_allowed(client, monkeypatch):
    """不带 project_id 的全局助手 -> 200（project_id 可选，仅在有值时校验成员）。"""
    h = await _reg_login(client, "global")

    captured = {}

    async def _side(message, project_id=None, context=None):
        captured["project_id"] = project_id
        return {"message": "全局回答", "confidence": 0.9}

    fake = AsyncMock(side_effect=_side)
    monkeypatch.setattr("app.services.ai_service.ai_service.chat", fake)

    r = await client.post(
        f"{BASE}/openclaw/assistant/chat", headers=h,
        json={"message": "项目管理最佳实践"},
    )
    assert r.status_code == 200, r.text
    assert fake.call_args is not None, "ai_service.chat 未被调用"
    assert captured.get("project_id") is None, "未传 project_id 时不应附带项目上下文"


async def test_f03_no_cross_project_leak(client, monkeypatch):
    """成员同时拥有 A、B 两项目，但仅以 A 的 project_id 对话 -> 响应不泄露 B。"""
    h = await _reg_login(client, "dual")
    pid_a = await _create_project(client, h, "F03-A")
    pid_b = await _create_project(client, h, "F03-B")

    captured = {}

    async def _side(message, project_id=None, context=None):
        captured["project_id"] = project_id
        return {"message": f"[ctx={project_id}] {message}", "confidence": 0.95}

    fake = AsyncMock(side_effect=_side)
    monkeypatch.setattr("app.services.ai_service.ai_service.chat", fake)

    r = await client.post(
        f"{BASE}/openclaw/assistant/chat", headers=h,
        json={"message": "只看 A", "project_id": pid_a},
    )
    assert r.status_code == 200, r.text
    assert captured.get("project_id") == pid_a
    assert pid_b not in data_of(r)["message"], "响应串入了未授权的 B 项目上下文（F-03 泄露）"

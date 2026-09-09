"""
冒烟测试 1：主路径端到端（happy path）

覆盖团队负责人列出的主路径：
- 登录 + /auth/me
- 列项目 / 创建项目 / 获取项目详情 / 更新状态 / 统计
- 创建任务 / 看板状态变更（PUT status=done）/ 软删
- AI 助手对话（/openclaw/assistant/chat，带 project_id）
- webhook inbound（/integrations/inbound/agent）

说明：
- AI 对话与 inbound/agent 内部调用大模型。为保证冒烟确定性（不因外部 LLM
  不可达而误报），默认用 monkeypatch + AsyncMock 桩替换 ai_service.chat /
  run_agent，仅校验「请求 -> 服务 -> 响应」链路与 project_id 透传。
  （用 AsyncMock 而非裸协程函数，避免实例属性绑定导致 self 被注入。）
- 若设置环境变量 SMOKE_LIVE_AI=1，则跳过桩、真正调用大模型（需网络/有效 Key）。

运行（在 backend/ 目录下）：
    ../../venv/Scripts/python -m pytest tests/test_smoke_e2e.py -v
"""
import os
import uuid
from unittest.mock import AsyncMock
from sqlalchemy import select

from app.main import app  # noqa: F401  (确保 app 被同一进程加载)
from app.db.session import async_session_maker
from app.models import User
from app.models.permission import Role, ProjectMember
from app.core.security import get_password_hash
from conftest import data_of

BASE = "/api/v1"
_LIVE_AI = os.environ.get("SMOKE_LIVE_AI", "") in ("1", "true", "True")


async def _reg_login(client, suffix: str) -> dict:
    """注册并登录，返回 Bearer 头。邮箱/用户名带 suffix 防重。"""
    email = f"smoke{suffix}@example.com"
    username = f"smoke{suffix}"
    await client.post(
        f"{BASE}/auth/register",
        json={
            "email": email, "username": username,
            "password": "Smoke123!", "full_name": f"冒烟{suffix}",
        },
    )
    r = await client.post(
        f"{BASE}/auth/login",
        json={"username": username, "password": "Smoke123!"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {data_of(r)['access_token']}"}


async def _create_project(client, headers, name="冒烟项目A") -> dict:
    r = await client.post(
        f"{BASE}/projects",
        headers=headers,
        json={"name": name, "description": "端到端冒烟", "priority": 3},
    )
    assert r.status_code in (200, 201), r.text
    return data_of(r)


async def _make_superuser(client, suffix: str) -> dict:
    """直接插入 is_superuser=True 用户（注册接口服务端强制 is_superuser=False）。"""
    email = f"sup_{suffix}@example.com"
    username = f"sup_{suffix}"
    async with async_session_maker() as db:
        u = User(
            email=email, username=username,
            hashed_password=get_password_hash("Sup1234!"),
            is_superuser=True, is_active=True, full_name=f"超管_{suffix}",
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
    r = await client.post(
        f"{BASE}/auth/login",
        json={"username": username, "password": "Sup1234!"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {data_of(r)['access_token']}"}


async def _add_active_member(db, user_id: str, project_id: str) -> None:
    """将 user 作为活跃成员加入 project。"""
    role = (await db.execute(select(Role).limit(1))).scalar_one_or_none()
    if role is None:
        role = Role(name=f"smk_role_{uuid.uuid4().hex[:8]}", permissions=[])
        db.add(role)
        await db.commit()
        await db.refresh(role)
    db.add(ProjectMember(
        project_id=project_id, user_id=user_id,
        role_id=role.id, is_active=True,
    ))
    await db.commit()


async def _me_uid(client, headers: dict) -> str:
    """取当前登录用户 id。"""
    r = await client.get(f"{BASE}/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    return data_of(r)["id"]


async def test_login_and_me(client):
    """登录后 /auth/me 返回 200 且含当前用户 id。"""
    h = await _reg_login(client, "me")
    r = await client.get(f"{BASE}/auth/me", headers=h)
    assert r.status_code == 200, r.text
    assert data_of(r).get("id"), "me 未返回 id"


async def test_project_lifecycle(client):
    """项目创建 -> 列表可见 -> 详情 -> 更新普通字段(验证 PUT 500 已修复) -> 统计。"""
    h = await _reg_login(client, "proj")
    p = await _create_project(client, h, "生命周期项目")
    pid = p["id"]

    r = await client.get(f"{BASE}/projects", headers=h)
    assert r.status_code == 200
    assert any(x["id"] == pid for x in data_of(r)["items"]), "列表未包含新建项目"

    r = await client.get(f"{BASE}/projects/{pid}", headers=h)
    assert r.status_code == 200, r.text
    assert data_of(r)["name"] == "生命周期项目"

    # 更新普通字段：此前因 ProjectUpdate 缺 owner_id 字段导致 500，现已修复
    r = await client.put(
        f"{BASE}/projects/{pid}", headers=h,
        json={"name": "生命周期项目(改)", "description": "改后描述", "status": "active"},
    )
    assert r.status_code == 200, r.text
    assert data_of(r)["name"] == "生命周期项目(改)"
    assert data_of(r)["status"] == "active"

    r = await client.get(f"{BASE}/projects/{pid}/statistics", headers=h)
    assert r.status_code == 200, r.text
    assert "task_count" in data_of(r)


async def test_task_and_kanban_status_change(client):
    """任务创建 -> 列表 -> 看板状态变更(done) -> 软删。"""
    h = await _reg_login(client, "task")
    p = await _create_project(client, h, "看板项目")
    pid = p["id"]

    r = await client.post(
        f"{BASE}/tasks",
        headers=h,
        json={"project_id": pid, "name": "实现登录接口", "status": "todo", "priority": 2},
    )
    assert r.status_code in (200, 201), r.text
    tid = data_of(r)["id"]
    assert data_of(r).get("wbs_code"), "未生成 WBS 编码"

    r = await client.get(f"{BASE}/tasks", headers=h, params={"project_id": pid})
    assert r.status_code == 200
    assert data_of(r)["total"] >= 1

    # 看板状态变更：应触发自动化/Webhook 且不报错
    r = await client.put(
        f"{BASE}/tasks/{tid}", headers=h,
        json={"status": "done", "progress": 100},
    )
    assert r.status_code == 200, r.text
    assert data_of(r)["status"] == "done"

    r = await client.delete(f"{BASE}/tasks/{tid}", headers=h)
    assert r.status_code == 200, r.text


async def test_ai_assistant_chat_member(client, monkeypatch):
    """成员带 project_id 调用 AI 助手：链路通 + project_id 透传到模型。"""
    h = await _reg_login(client, "aichat")
    p = await _create_project(client, h, "AI对话项目")
    pid = p["id"]

    if _LIVE_AI:
        r = await client.post(
            f"{BASE}/openclaw/assistant/chat", headers=h,
            json={"message": "列出本项目本周任务", "project_id": pid},
        )
        assert r.status_code in (200, 502, 503), r.text
        return

    captured = {}

    async def _side(message, project_id=None, context=None):
        captured["project_id"] = project_id
        captured["message"] = message
        return {"message": f"[stub pid={project_id}] 已收到：{message}", "confidence": 0.95}

    fake = AsyncMock(side_effect=_side)
    monkeypatch.setattr("app.services.ai_service.ai_service.chat", fake)

    r = await client.post(
        f"{BASE}/openclaw/assistant/chat", headers=h,
        json={"message": "列出本项目本周任务", "project_id": pid},
    )
    assert r.status_code == 200, r.text
    assert data_of(r).get("message"), "AI 响应为空"
    assert fake.call_args is not None, "ai_service.chat 未被调用"
    assert captured.get("project_id") == pid, "project_id 未透传到模型（F-03 链路断裂）"


async def test_webhook_inbound_agent(client, monkeypatch):
    """inbound/agent：连接器文本 -> Agent 解析建任务（壁垒 C 闭环）。"""
    h = await _reg_login(client, "inbound")
    p = await _create_project(client, h, "入站项目")
    pid = p["id"]

    if _LIVE_AI:
        r = await client.post(
            f"{BASE}/integrations/inbound/agent", headers=h,
            json={"provider": "dingtalk", "project_id": pid,
                  "content": "会议纪要：下周三前完成登录模块联调"},
        )
        assert r.status_code in (200, 502, 503), r.text
        return

    captured = {}

    async def _side(agent_name, db, user_id, project_id, content, opts):
        captured["project_id"] = project_id
        captured["agent"] = agent_name
        return {"created_tasks": [], "agent": agent_name}

    fake = AsyncMock(side_effect=_side)
    monkeypatch.setattr("app.services.ai.out_of_box_agents.run_agent", fake)

    r = await client.post(
        f"{BASE}/integrations/inbound/agent", headers=h,
        json={"provider": "dingtalk", "project_id": pid,
              "content": "会议纪要：下周三前完成登录模块联调"},
    )
    assert r.status_code == 200, r.text
    assert data_of(r).get("success") is True, r.text
    assert fake.call_args is not None, "run_agent 未被调用"
    assert captured.get("project_id") == pid, "inbound 的 project_id 未传入 Agent"


async def test_project_update_owner_by_superuser(client):
    """超管可变更项目所有者 -> 200，响应 owner_id 更新为新 owner。

    同时验证 projects.py:225 的 owner_id 转让守卫对超管放行（不 403）。
    """
    h_a = await _reg_login(client, "updA")
    pid = (await _create_project(client, h_a, "Owner变更项目"))["id"]
    h_c = await _reg_login(client, "updC")
    c_uid = await _me_uid(client, h_c)
    h_sup = await _make_superuser(client, "updS")
    r = await client.put(
        f"{BASE}/projects/{pid}", headers=h_sup,
        json={"owner_id": c_uid},
    )
    assert r.status_code == 200, r.text
    assert data_of(r).get("owner_id") == c_uid, "超管变更 owner 后响应未反映新 owner"


async def test_project_update_owner_by_non_superuser_member_forbidden(client):
    """非超管成员变更所有者 -> 403（仅管理员可转让，projects.py:225-230 守卫）。"""
    h_a = await _reg_login(client, "ownA")
    pid = (await _create_project(client, h_a, "转让项目"))["id"]
    h_b = await _reg_login(client, "memB")
    b_uid = await _me_uid(client, h_b)
    h_c = await _reg_login(client, "tgtC")
    c_uid = await _me_uid(client, h_c)
    async with async_session_maker() as db:
        await _add_active_member(db, b_uid, pid)
    r = await client.put(
        f"{BASE}/projects/{pid}", headers=h_b,
        json={"owner_id": c_uid},
    )
    assert r.status_code == 403, f"期望 403，得到 {r.status_code}: {r.text}"

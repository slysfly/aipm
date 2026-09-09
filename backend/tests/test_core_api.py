"""
核心 API 端到端测试

覆盖 7 个核心 API 场景：
1. test_health_check       - 健康检查
2. test_auth_login         - 登录认证（含成功/失败/Token校验）
3. test_project_crud       - 项目增删改查
4. test_task_crud          - 任务增删改查
5. test_risk_crud          - 风险增删改查
6. test_agent_list         - Agent 能力目录查询
7. test_llm_config         - LLM 配置查询
"""

import pytest

from conftest import data_of


# =========================================================================== #
# 1. 健康检查
# =========================================================================== #

async def test_health_check(client):
    """验证 /health 返回正常状态"""
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert "timestamp" in body
    assert "version" in body


# =========================================================================== #
# 2. 登录认证
# =========================================================================== #

async def test_auth_login(client):
    """注册新用户 -> 登录 -> 获取 Token -> 验证 /auth/me"""
    import time
    suffix = str(int(time.time() * 1000))
    username = f"core_api_user_{suffix}"
    email = f"{username}@test.com"

    # 注册
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "TestPass123!",
            "full_name": "核心API测试用户",
        },
    )
    assert r.status_code in (200, 201), r.text

    # 登录
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "TestPass123!"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    data = body.get("data", body)
    assert "access_token" in data
    assert "refresh_token" in data
    access_token = data["access_token"]

    # 用 Token 访问 /auth/me
    headers = {"Authorization": f"Bearer {access_token}"}
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["username"] == username

    # 错误密码登录返回 401
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "wrong_password"},
    )
    assert r.status_code == 401


# =========================================================================== #
# 3. 项目 CRUD
# =========================================================================== #

async def test_project_crud(client, auth_headers):
    """项目创建 / 列表 / 详情 / 更新 / 删除"""

    # -- 创建 --
    r = await client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={
            "name": "核心API测试项目",
            "description": "用于验证项目CRUD功能",
            "industry_type": "it_software",
            "priority": 2,
        },
    )
    assert r.status_code == 201, r.text
    body = data_of(r)
    pid = body["id"]
    assert body["name"] == "核心API测试项目"

    # -- 列表 --
    r = await client.get("/api/v1/projects", headers=auth_headers)
    assert r.status_code == 200
    items = data_of(r).get("items", [])
    assert any(p["id"] == pid for p in items)

    # -- 详情 --
    r = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert r.status_code == 200
    assert data_of(r)["name"] == "核心API测试项目"

    # -- 更新 --
    r = await client.put(
        f"/api/v1/projects/{pid}",
        headers=auth_headers,
        json={"status": "active", "priority": 1},
    )
    assert r.status_code == 200
    assert data_of(r)["status"] == "active"

    # -- 统计 --
    r = await client.get(f"/api/v1/projects/{pid}/statistics", headers=auth_headers)
    assert r.status_code == 200


# =========================================================================== #
# 4. 任务 CRUD
# =========================================================================== #

async def test_task_crud(client, auth_headers):
    """任务创建 / 列表 / 更新状态 / 删除"""

    # 先创建项目
    p = await client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "任务测试项目", "priority": 2},
    )
    pid = data_of(p)["id"]

    # -- 创建 --
    r = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={
            "project_id": pid,
            "name": "实现核心API测试接口",
            "status": "todo",
            "priority": 2,
            "estimated_hours": 16,
        },
    )
    assert r.status_code == 201, r.text
    tid = data_of(r)["id"]
    assert data_of(r)["wbs_code"]  # WBS 编码自动生成
    assert data_of(r)["name"] == "实现核心API测试接口"

    # -- 列表 --
    r = await client.get(
        "/api/v1/tasks",
        headers=auth_headers,
        params={"project_id": pid},
    )
    assert r.status_code == 200
    assert data_of(r)["total"] >= 1

    # -- 更新状态 --
    r = await client.put(
        f"/api/v1/tasks/{tid}",
        headers=auth_headers,
        json={"status": "in_progress", "progress": 50},
    )
    assert r.status_code == 200
    assert data_of(r)["status"] == "in_progress"
    assert float(data_of(r)["progress"]) == 50

    # -- 完成任务 --
    r = await client.put(
        f"/api/v1/tasks/{tid}",
        headers=auth_headers,
        json={"status": "done", "progress": 100},
    )
    assert r.status_code == 200
    assert data_of(r)["status"] == "done"

    # -- 删除（软删除） --
    r = await client.delete(f"/api/v1/tasks/{tid}", headers=auth_headers)
    assert r.status_code == 200


# =========================================================================== #
# 5. 风险 CRUD
# =========================================================================== #

async def test_risk_crud(client, auth_headers):
    """风险创建 / 列表 / 更新 / 删除"""

    # 先创建项目
    p = await client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "风险测试项目", "priority": 2},
    )
    pid = data_of(p)["id"]

    # -- 创建 --
    r = await client.post(
        "/api/v1/risks",
        headers=auth_headers,
        json={
            "project_id": pid,
            "name": "开发资源不足风险",
            "description": "核心开发人员可能被其他项目占用",
            "category": "resource",
            "probability": 0.6,
            "impact": 0.7,
            "status": "identified",
        },
    )
    assert r.status_code == 201, r.text
    risk_id = data_of(r)["id"]
    assert data_of(r)["name"] == "开发资源不足风险"

    # -- 列表（按项目） --
    r = await client.get(
        "/api/v1/risks",
        headers=auth_headers,
        params={"project_id": pid},
    )
    assert r.status_code == 200
    risks = data_of(r)
    assert any(risk["id"] == risk_id for risk in risks)

    # -- 详情 --
    r = await client.get(f"/api/v1/risks/{risk_id}", headers=auth_headers)
    assert r.status_code == 200
    assert data_of(r)["name"] == "开发资源不足风险"

    # -- 更新 --
    r = await client.put(
        f"/api/v1/risks/{risk_id}",
        headers=auth_headers,
        json={"status": "mitigating", "response_strategy": "mitigate"},
    )
    assert r.status_code == 200
    assert data_of(r)["status"] == "mitigating"

    # -- 删除 --
    r = await client.delete(f"/api/v1/risks/{risk_id}", headers=auth_headers)
    assert r.status_code == 200
    assert data_of(r)["ok"] is True

    # 删除后查询应返回 404
    r = await client.get(f"/api/v1/risks/{risk_id}", headers=auth_headers)
    assert r.status_code == 404


# =========================================================================== #
# 6. Agent 列表查询
# =========================================================================== #

async def test_agent_list(client, auth_headers):
    """获取 AI Agent 能力目录"""
    r = await client.get("/api/v1/agents", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    # 响应以 items 作为列表键名
    agents = body.get("items", body.get("agents", body))
    assert len(agents) > 0

    # 验证包含预定义的 Agent
    agent_ids = {a["id"] for a in agents}
    for expected_id in ("evm", "risk", "report", "resource", "wbs", "quality", "compliance",
                        "meeting_minutes"):
        assert expected_id in agent_ids, f"Agent [{expected_id}] 不存在于返回列表中"

    # 验证每个 Agent 包含必要字段
    for agent in agents:
        assert "id" in agent
        assert "name" in agent
        assert "description" in agent
        assert "accuracy" in agent


# =========================================================================== #
# 7. LLM 配置查询
# =========================================================================== #

async def test_llm_config(client, auth_headers):
    """LLM 配置列表查询 + Provider 列表查询"""
    # -- 列表（初始为空） --
    r = await client.get("/api/v1/llm-configs/", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body

    # -- Provider 列表 --
    r = await client.get("/api/v1/llm-configs/providers", headers=auth_headers)
    assert r.status_code == 200
    providers_body = r.json()
    # 响应可能是 {"providers": [...]} 或直接是列表
    providers = providers_body.get("providers", providers_body)
    assert len(providers) > 0
    provider_names = {p["name"] for p in providers}
    for expected in ("openai", "deepseek", "anthropic", "zhipu", "baidu"):
        assert expected in provider_names, f"Provider [{expected}] 不存在"

"""集成（OAuth 真实化/诚实报错）与 AI 降级测试"""

from conftest import data_of


async def test_integrations_list(client, auth_headers):
    r = await client.get("/api/v1/integrations", headers=auth_headers)
    assert r.status_code == 200
    providers = r.json()["data"]
    assert isinstance(providers, list) and len(providers) >= 7


async def test_integration_connect_rejects_mock_code(client, auth_headers):
    # 使用 mock 授权码应被后端拒绝（诚实报错，而非伪造"已连接"）
    r = await client.post(
        "/api/v1/integrations/github/connect",
        headers=auth_headers,
        json={"code": "mock_abc123"},
    )
    assert r.status_code >= 400, "mock 授权码不应被接受"
    body = r.json()
    assert "connected" not in (body.get("data") or {})


async def test_ai_generate_wbs_graceful(client, auth_headers):
    # 未配置 AI Key 时应优雅返回 503（而非 500 或伪造结果）
    p = await client.post("/api/v1/projects", headers=auth_headers, json={"name": "WBS项目", "priority": 3})
    pid = data_of(p)["id"]

    r = await client.post(
        "/api/v1/ai/generate-wbs",
        headers=auth_headers,
        json={"project_name": "示例", "industry_type": "it_software", "project_id": pid, "save_to_tasks": True},
    )
    # 200: 已配置 Key 且写入任务；503: 未配置 Key 优雅降级
    assert r.status_code in (200, 503), r.text
    if r.status_code == 200:
        body = data_of(r)
        # 兼容三种响应结构：旧版 created_task_count / 新版 WBS 结构化数据 / 异步任务态（返回 task_id）
        assert (
            "task_id" in body
            or "created_task_count" in body
            or "tasks" in body
            or "wbs_structure" in body
        ), f"未知响应结构：{body}"


async def test_ai_chat_graceful(client, auth_headers):
    r = await client.post(
        "/api/v1/ai/chat",
        headers=auth_headers,
        json={"message": "你好", "project_id": None},
    )
    assert r.status_code in (200, 503)

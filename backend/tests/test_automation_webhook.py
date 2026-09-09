"""自动化规则与 Webhook 业务联动测试（验证数据真正打通）"""

from conftest import data_of


async def test_automation_triggered_on_task_create(client, auth_headers):
    # 当前用户（通知将发给任务负责人，即当前用户，便于校验）
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    uid = data_of(me)["id"]

    # 1) 创建项目
    p = await client.post("/api/v1/projects", headers=auth_headers, json={"name": "自动化项目", "priority": 3})
    pid = data_of(p)["id"]

    # 2) 创建自动化规则：任务创建 -> 发送站内通知（不指定接收人，自动通知负责人）
    rule = await client.post(
        "/api/v1/automations",
        headers=auth_headers,
        json={
            "name": "任务创建通知",
            "trigger_type": "task_created",
            "trigger_conditions": {},
            "actions": [
                {"type": "send_notification", "title": "新任务", "content": "任务 {{task.name}} 已创建"}
            ],
            "project_id": pid,
            "is_active": True,
        },
    )
    assert rule.status_code == 201, rule.text
    rule_id = data_of(rule)["id"]

    # 3) 创建任务（指定负责人为当前用户，应同步触发自动化，写入通知表）
    t = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"project_id": pid, "name": "被自动化的任务", "status": "todo", "assignee_id": uid},
    )
    assert t.status_code == 201

    # 4) 验证通知已生成（数据从 任务创建 -> 自动化 -> 通知表 真正联通）
    n = await client.get("/api/v1/notifications", headers=auth_headers)
    assert n.status_code == 200
    notifications = data_of(n)["items"]
    assert any("新任务" == x["title"] or "被自动化的任务" in (x["content"] or "") for x in notifications)


async def test_automation_test_endpoint(client, auth_headers):
    p = await client.post("/api/v1/projects", headers=auth_headers, json={"name": "规则测试项目", "priority": 3})
    pid = data_of(p)["id"]
    t = await client.post("/api/v1/tasks", headers=auth_headers, json={"project_id": pid, "name": "样本任务", "status": "todo"})
    tid = data_of(t)["id"]

    rule = await client.post(
        "/api/v1/automations",
        headers=auth_headers,
        json={
            "name": "测试规则", "trigger_type": "task_created",
            "actions": [{"type": "send_notification", "title": "t", "content": "c"}],
        },
    )
    rule_id = data_of(rule)["id"]

    r = await client.post(
        f"/api/v1/automations/{rule_id}/test",
        headers=auth_headers,
        json={"entity_type": "task", "entity_id": tid, "trigger_data": {}},
    )
    assert r.status_code == 200
    assert "triggered" in data_of(r)


async def test_webhook_crud(client, auth_headers):
    wh = await client.post(
        "/api/v1/webhooks",
        headers=auth_headers,
        json={"name": "测试Hook", "url": "https://example.com/hook", "events": ["task.created"], "is_active": True},
    )
    assert wh.status_code in (200, 201), wh.text
    wh_id = data_of(wh)["id"]

    lst = await client.get("/api/v1/webhooks", headers=auth_headers)
    assert lst.status_code == 200
    assert any(w["id"] == wh_id for w in data_of(lst)["items"])

    # 测试投递（外部地址不可达时返回失败结果，但不应 500 崩溃）
    test_r = await client.post(f"/api/v1/webhooks/{wh_id}/test", headers=auth_headers, json={})
    assert test_r.status_code == 200
    assert "success" in data_of(test_r)

"""项目 / 任务 CRUD 与业务联动测试"""

from conftest import data_of


async def test_project_crud(client, auth_headers):
    # 创建
    r = await client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "测试项目A", "description": "单元测试用例", "industry_type": "it_software", "priority": 3},
    )
    assert r.status_code == 201, r.text
    pid = data_of(r)["id"]

    # 列表
    r = await client.get("/api/v1/projects", headers=auth_headers)
    assert r.status_code == 200
    assert any(p["id"] == pid for p in data_of(r)["items"])

    # 详情
    r = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert r.status_code == 200
    assert data_of(r)["name"] == "测试项目A"

    # 更新
    r = await client.put(f"/api/v1/projects/{pid}", headers=auth_headers, json={"status": "active"})
    assert r.status_code == 200
    assert data_of(r)["status"] == "active"

    # 统计
    r = await client.get(f"/api/v1/projects/{pid}/statistics", headers=auth_headers)
    assert r.status_code == 200


async def test_task_crud_and_status_change(client, auth_headers):
    # 准备项目
    p = await client.post("/api/v1/projects", headers=auth_headers, json={"name": "任务项目", "priority": 2})
    pid = data_of(p)["id"]

    # 创建任务
    r = await client.post(
        "/api/v1/tasks",
        headers=auth_headers,
        json={"project_id": pid, "name": "实现登录接口", "status": "todo", "priority": 2},
    )
    assert r.status_code == 201, r.text
    tid = data_of(r)["id"]
    assert data_of(r)["wbs_code"]  # WBS 编码已生成

    # 列表
    r = await client.get("/api/v1/tasks", headers=auth_headers, params={"project_id": pid})
    assert r.status_code == 200
    assert data_of(r)["total"] >= 1

    # 更新状态（应触发自动化/Webhook，且不报错）
    r = await client.put(f"/api/v1/tasks/{tid}", headers=auth_headers, json={"status": "done", "progress": 100})
    assert r.status_code == 200
    assert data_of(r)["status"] == "done"

    # 删除（软删）
    r = await client.delete(f"/api/v1/tasks/{tid}", headers=auth_headers)
    assert r.status_code == 200

"""MCP 协议真实化测试（工具/资源基于真实数据库）"""
import json

from conftest import data_of


async def _mcp_init(client, headers=None):
    """MCP 协议要求先完成 initialize 握手，后续 tools/list、tools/call、resources/read 才可用"""
    r = await client.post(
        "/api/v1/mcp/initialize",
        json={"jsonrpc": "2.0", "id": "init", "method": "initialize", "params": {}},
        headers=headers,
    )
    assert r.status_code == 200


async def test_mcp_status(client, auth_headers):
    r = await client.get("/api/v1/mcp/status", headers=auth_headers)
    assert r.status_code == 200
    body = data_of(r)
    assert body["status"] == "running"
    assert body["tools_count"] >= 5
    assert body["resources_count"] >= 1


async def test_mcp_tools_list(client, auth_headers):
    await _mcp_init(client, headers=auth_headers)
    r = await client.post(
        "/api/v1/mcp/tools/list",
        json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = data_of(r)
    assert "result" in body, body
    tools = body["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"create_task", "query_tasks", "create_project", "generate_report"}.issubset(names)


async def test_mcp_create_project_real_db(client, auth_headers):
    await _mcp_init(client, headers=auth_headers)
    r = await client.post(
        "/api/v1/mcp/tools/call",
        json={
            "jsonrpc": "2.0", "id": "2", "method": "tools/call",
            "params": {"name": "create_project", "arguments": {"name": "MCP项目"}},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = data_of(r)
    assert "result" in body, body
    # MCP 标准：工具返回值被序列化在 result["content"][0]["text"]
    result = body["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["success"] is True
    assert payload["data"]["id"]

    # 验证确实落库（可通过列表接口查到）
    pid = payload["data"]["id"]
    get_r = await client.get(f"/api/v1/projects/{pid}", headers=auth_headers)
    assert get_r.status_code == 200


async def test_mcp_metrics_resource(client, auth_headers):
    await _mcp_init(client, headers=auth_headers)
    r = await client.post(
        "/api/v1/mcp/resources/read",
        json={"jsonrpc": "2.0", "id": "3", "method": "resources/read", "params": {"uri": "metrics://overview"}},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = data_of(r)
    assert "result" in body, body
    # MCP 标准：资源内容序列化在 result["contents"][0]["text"]
    data = json.loads(body["result"]["contents"][0]["text"])
    assert "metrics" in data
    assert "total_projects" in data["metrics"]

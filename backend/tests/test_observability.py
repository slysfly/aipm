"""
可观测性测试：X-Request-ID / Prometheus /metrics / JSON 日志格式
对应 app/core/observability.py 与 app/core/logging.py 的扩展。

注意：所有对全局 settings 的修改均经 monkeypatch（自动还原），
避免测试顺序耦合污染其他用例。
"""

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.core.logging import JsonFormatter, RequestIdFilter, setup_logging
from app.core.observability import request_id_var, setup_observability


@pytest.fixture
def bare_app(monkeypatch):
    """轻量应用（不依赖数据库）：验证中间件行为"""
    monkeypatch.setattr(settings, "METRICS_ENABLED", False)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "")
    app = FastAPI()
    setup_observability(app)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    return app


@pytest.fixture
def obs_app(monkeypatch):
    """独立应用：开启 metrics，便于在不影响全局 app 的情况下测试端点门控"""
    monkeypatch.setattr(settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(settings, "METRICS_TOKEN", "")
    app = FastAPI()
    setup_observability(app)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    return app


def test_request_id_generated_and_returned(bare_app):
    """未携带 X-Request-ID 时自动生成，并回写到响应头"""
    r = TestClient(bare_app).get("/ping")
    assert r.status_code == 200
    assert "x-request-id" in r.headers
    assert len(r.headers["x-request-id"]) == 16


def test_request_id_inbound_is_echoed(bare_app):
    """入站携带 X-Request-ID 时透传（网关/前端生成的链路 ID）"""
    r = TestClient(bare_app).get("/ping", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers["x-request-id"] == "trace-abc-123"


def test_metrics_endpoint_serves_prometheus_text(obs_app):
    client = TestClient(obs_app)
    client.get("/ping")
    r = client.get("/metrics")
    assert r.status_code == 200
    # Content-Type 必须与 prometheus_client 的规范值完全一致（不能出现重复 charset 参数，
    # 否则真实 Prometheus 服务端解析时会拒收）
    assert r.headers["content-type"] == "text/plain; version=1.0.0; charset=utf-8"
    body = r.text
    assert "aipm_http_requests_total" in body
    # route 标签使用路由模板而非原始路径
    assert 'route="/ping"' in body
    assert "aipm_http_request_duration_seconds" in body
    assert "aipm_http_requests_in_flight" in body


def test_route_label_uses_path_template(obs_app):
    """路径参数收敛为路由模板，避免标签基数爆炸（README 核心卖点）"""
    @obs_app.get("/items/{item_id}")
    async def item(item_id: int):
        return {"id": item_id}

    client = TestClient(obs_app)
    client.get("/items/42")
    client.get("/items/99")
    body = client.get("/metrics").text
    assert 'route="/items/{item_id}"' in body
    # 原始路径不应作为标签出现
    assert 'route="/items/42"' not in body


def test_metrics_token_required_when_configured(obs_app, monkeypatch):
    monkeypatch.setattr(settings, "METRICS_TOKEN", "secret-token")
    client = TestClient(obs_app)
    assert client.get("/metrics").status_code == 401
    # 错误 token 同样拒绝
    wrong = client.get("/metrics", headers={"Authorization": "Bearer wrong"})
    assert wrong.status_code == 401
    ok = client.get("/metrics", headers={"Authorization": "Bearer secret-token"})
    assert ok.status_code == 200


def test_metrics_disabled_by_default(monkeypatch):
    """默认（METRICS_ENABLED=false）不注册 /metrics"""
    # 代码级默认值为 False（与运行环境变量无关）
    assert Settings.__fields__["METRICS_ENABLED"].default is False
    monkeypatch.setattr(settings, "METRICS_ENABLED", False)
    app = FastAPI()
    setup_observability(app)
    assert TestClient(app).get("/metrics").status_code == 404


def test_exception_path_records_metrics(obs_app):
    """未处理异常：计入异常计数与 500，且返回 500 响应"""
    @obs_app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    client = TestClient(obs_app, raise_server_exceptions=False)
    r = client.get("/boom")
    assert r.status_code == 500
    body = client.get("/metrics").text
    assert "aipm_http_exceptions_total" in body
    assert 'type="RuntimeError"' in body


def test_json_formatter_contains_request_id():
    """JSON 日志格式包含 request_id 字段（来自 contextvar）；extra 显式传入优先"""
    token = request_id_var.set("rid-for-test")
    try:
        record = logging.LogRecord(
            name="test.obs", level=logging.INFO, pathname=__file__, lineno=1,
            msg="with rid", args=(), exc_info=None,
        )
        RequestIdFilter().filter(record)
        assert record.request_id == "rid-for-test"
        payload = json.loads(JsonFormatter().format(record))
        assert payload["request_id"] == "rid-for-test"
        assert payload["msg"] == "with rid"
        assert payload["level"] == "INFO"

        # extra 显式携带的 request_id（兜底 handler 场景）优先于 contextvar
        record2 = logging.LogRecord(
            name="test.obs", level=logging.ERROR, pathname=__file__, lineno=2,
            msg="from state", args=(), exc_info=None,
        )
        record2.request_id = "rid-from-request-state"
        RequestIdFilter().filter(record2)
        assert json.loads(JsonFormatter().format(record2))["request_id"] == "rid-from-request-state"
    finally:
        request_id_var.reset(token)

    # 无请求上下文时为 "-"
    record3 = logging.LogRecord(
        name="test.obs", level=logging.INFO, pathname=__file__, lineno=3,
        msg="no ctx", args=(), exc_info=None,
    )
    RequestIdFilter().filter(record3)
    assert json.loads(JsonFormatter().format(record3))["request_id"] == "-"


def test_setup_logging_returns_root_logger():
    """setup_logging 正常返回根 logger；前后恢复 root handlers 避免影响其他测试"""
    root = logging.getLogger()
    saved = list(root.handlers)
    try:
        result = setup_logging()
        assert result is root
        assert root.handlers, "应至少配置一个处理器"
        # 每个处理器都挂了 request_id 过滤器
        assert all(any(isinstance(f, RequestIdFilter) for f in h.filters) for h in root.handlers)
    finally:
        root.handlers = saved

"""
v0.1.0 评审修复的针对性测试：
- paths.data_path 防穿越收口
- 钉钉 Webhook 签名按官方算法（timestamp + "\\n" + secret）可验过、错签名被拒
- /metrics Content-Type 无重复 charset（真实 Prometheus 可抓取）
- METRICS_* 经 Settings（.env）生效，不再只认进程环境变量
"""

import base64
import hashlib
import hmac
import sys
import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest


def _make_request(headers: dict) -> StarletteRequest:
    encoded = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return StarletteRequest({"type": "http", "method": "POST", "headers": encoded, "query_string": b""})


# ---------------------------------------------------------------------------
# paths.data_path 防穿越
# ---------------------------------------------------------------------------
def test_paths_data_path_containment():
    from app import paths

    ok = paths.data_path("tool_outputs", "p1", "a.md")
    assert paths.DATA_DIR in ok.resolve().parents or ok.resolve() == paths.DATA_DIR.resolve()

    with pytest.raises(ValueError):
        paths.data_path("tool_outputs", "..", "..", "escape.md")

    abs_seg = "C:/evil" if sys.platform == "win32" else "/evil"
    with pytest.raises(ValueError):
        paths.data_path("tool_outputs", abs_seg, "x.md")


# ---------------------------------------------------------------------------
# 钉钉签名：官方算法 stringToSign = f"{timestamp}\n{secret}"
# ---------------------------------------------------------------------------
async def test_dingtalk_signature_official_algorithm():
    from app.api.v1.im_gateway import _verify_im_signature
    from app.models.im_gateway import IMProviderConfig

    secret = "sec-test-123"
    ts = int(time.time())
    sign = base64.b64encode(
        hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
    ).decode()

    config = IMProviderConfig(provider="dingtalk", app_id="x", app_secret=secret)

    # 官方算法计算的签名应通过（不抛异常即通过）
    await _verify_im_signature("dingtalk", config, _make_request({"timestamp": str(ts), "sign": sign}), b"body")

    # 错误签名被拒（403）
    bad = _make_request({"timestamp": str(ts), "sign": "AAAA" + sign[4:]})
    with pytest.raises(HTTPException) as ei:
        await _verify_im_signature("dingtalk", config, bad, b"body")
    assert ei.value.status_code == 403


# ---------------------------------------------------------------------------
# /metrics：Content-Type 与 Settings 化配置
# ---------------------------------------------------------------------------
def _metrics_app(monkeypatch, token: str) -> TestClient:
    from app.config import settings as app_settings
    from app.core.observability import install_metrics_route

    monkeypatch.setattr(app_settings, "METRICS_ENABLED", True)
    monkeypatch.setattr(app_settings, "METRICS_TOKEN", token)
    app = FastAPI()
    install_metrics_route(app)
    return TestClient(app)


def test_metrics_content_type_no_duplicate_charset(monkeypatch):
    client = _metrics_app(monkeypatch, "tk")
    r = client.get("/metrics", headers={"Authorization": "Bearer tk"})
    assert r.status_code == 200, r.text
    ct = r.headers["content-type"]
    # 与 prometheus_client 规范值完全一致；starlette 不得再追加第二个 charset
    # （重复参数会被 Go mime.ParseMediaType 拒收 → 真实 Prometheus 抓取失败）
    assert ct == "text/plain; version=0.0.4; charset=utf-8"
    assert ct.count("charset") == 1


def test_metrics_config_via_settings(monkeypatch):
    """METRICS_* 写进 Settings（即 .env）即可生效，未带/错令牌一律 403"""
    client = _metrics_app(monkeypatch, "tk2")
    assert client.get("/metrics").status_code == 403
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 403
    assert client.get("/metrics", headers={"Authorization": "Bearer tk2"}).status_code == 200

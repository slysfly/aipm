"""
官方插件：Webhook 触发器

当项目事件触发时，向配置的 URL 发送 HTTP 请求（best-effort）。
支持可选签名密钥，对请求体做 HMAC-SHA256 签名写入 ``X-Signature`` 头。
"""

import json
import hmac
import hashlib
import logging
from typing import Dict, Any

import httpx

from app.services.integrations.plugin_sdk import BasePlugin, register_plugin

logger = logging.getLogger(__name__)

# 配置 JSON Schema：描述安装该插件时需要用户填写的配置项
WEBHOOK_CONFIG_SCHEMA = {
    "type": "object",
    "title": "Webhook 插件配置",
    "properties": {
        "url": {
            "type": "string",
            "format": "uri",
            "title": "回调地址",
            "description": "触发时接收 HTTP 请求的目标 URL",
        },
        "method": {
            "type": "string",
            "enum": ["POST", "PUT"],
            "default": "POST",
            "title": "请求方法",
        },
        "headers": {
            "type": "object",
            "title": "自定义请求头",
            "description": "键值对，例如 {\"X-Tenant\": \"acme\"}",
        },
        "secret": {
            "type": "string",
            "title": "签名密钥（可选）",
            "description": "填写后对请求体做 HMAC-SHA256 签名，结果写入 X-Signature 头",
        },
    },
    "required": ["url"],
}


class WebhookPlugin(BasePlugin):
    """向指定 URL 发送 HTTP 回调的通用触发器。"""

    def __init__(self):
        self.id = "webhook"
        self.name = "Webhook 触发器"
        self.description = "项目事件触发时，向配置的 URL 发送 HTTP 请求（best-effort）。"
        self.category = "automation"
        self.version = "1.0.0"
        self.config_schema = WEBHOOK_CONFIG_SCHEMA

    async def execute(self, context: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        url = config.get("url")
        if not url:
            return {"ok": False, "error": "缺少配置 url"}

        method = str(config.get("method", "POST")).upper()
        payload = json.dumps(context, ensure_ascii=False, default=str).encode("utf-8")

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        headers.update({str(k): str(v) for k, v in (config.get("headers") or {}).items()})

        # 可选：对请求体做 HMAC-SHA256 签名
        if config.get("secret"):
            sig = hmac.new(
                str(config["secret"]).encode("utf-8"), payload, hashlib.sha256
            ).hexdigest()
            headers["X-Signature"] = f"sha256={sig}"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if method == "PUT":
                    resp = await client.put(url, content=payload, headers=headers)
                else:
                    resp = await client.post(url, content=payload, headers=headers)
            return {
                "ok": True,
                "status_code": resp.status_code,
                "response": resp.text[:500],
            }
        except Exception as e:  # best-effort：捕获所有异常，记录并返回失败
            logger.exception("Webhook 插件调用失败: %s", url)
            return {"ok": False, "error": str(e)}


register_plugin(WebhookPlugin())

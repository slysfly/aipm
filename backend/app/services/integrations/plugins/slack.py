"""
官方插件：Slack 通知

通过 Slack Incoming Webhook 向频道发送消息。
"""

import json
import logging
from typing import Dict, Any, Optional

import httpx

from app.services.integrations.plugin_sdk import BasePlugin, register_plugin

logger = logging.getLogger(__name__)

SLACK_CONFIG_SCHEMA = {
    "type": "object",
    "title": "Slack 插件配置",
    "properties": {
        "webhook_url": {
            "type": "string",
            "format": "uri",
            "title": "Incoming Webhook URL",
            "description": "Slack 应用生成的 Incoming Webhook 地址",
        },
        "channel": {
            "type": "string",
            "title": "频道（可选）",
            "description": "例如 #alerts，覆盖 Webhook 默认频道",
        },
        "username": {
            "type": "string",
            "title": "显示名称（可选）",
        },
        "text_template": {
            "type": "string",
            "title": "消息模板（可选）",
            "description": "支持用 {project_id} {event} {user_id} 等占位符引用 context",
        },
    },
    "required": ["webhook_url"],
}


class SlackPlugin(BasePlugin):
    """向 Slack Incoming Webhook 发送消息。"""

    def __init__(self):
        self.id = "slack"
        self.name = "Slack 通知"
        self.description = "通过 Slack Incoming Webhook 向频道发送项目事件通知。"
        self.category = "integration"
        self.version = "1.0.0"
        self.config_schema = SLACK_CONFIG_SCHEMA

    @staticmethod
    def _render(template: Optional[str], context: Dict[str, Any]) -> str:
        if not template:
            return (
                f"项目事件通知：{context.get('event', 'trigger')} "
                f"(project={context.get('project_id')}, user={context.get('user_id')})"
            )
        try:
            return str(template).format(**context)
        except Exception:
            return str(template)

    async def execute(self, context: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        url = config.get("webhook_url")
        if not url:
            return {"ok": False, "error": "缺少配置 webhook_url"}

        payload: Dict[str, Any] = {"text": self._render(config.get("text_template"), context)}
        if config.get("channel"):
            payload["channel"] = config["channel"]
        if config.get("username"):
            payload["username"] = config["username"]

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
            return {"ok": True, "status_code": resp.status_code}
        except Exception as e:
            logger.exception("Slack 插件调用失败")
            return {"ok": False, "error": str(e)}


register_plugin(SlackPlugin())

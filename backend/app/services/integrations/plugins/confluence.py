"""
官方插件：Confluence 集成

调用 Confluence Cloud REST API（使用 邮箱 + API Token 做 Basic 认证）：
- create_page：在指定空间创建页面
- add_comment：给指定页面添加评论
"""

import json
import logging
from typing import Dict, Any, Optional

import httpx

from app.services.integrations.plugin_sdk import BasePlugin, register_plugin

logger = logging.getLogger(__name__)

CONFLUENCE_API_PATH = "/rest/api/content"

CONFLUENCE_CONFIG_SCHEMA = {
    "type": "object",
    "title": "Confluence 插件配置",
    "properties": {
        "base_url": {
            "type": "string",
            "format": "uri",
            "title": "Confluence 基础地址",
            "description": "例如 https://your-domain.atlassian.net",
        },
        "email": {"type": "string", "title": "账号邮箱"},
        "api_token": {"type": "string", "title": "API Token"},
        "space_key": {"type": "string", "title": "空间 Key"},
        "action": {
            "type": "string",
            "enum": ["create_page", "add_comment"],
            "default": "create_page",
            "title": "执行动作",
        },
        "parent_id": {
            "type": "string",
            "title": "父页面 ID（创建页面时可选）",
        },
        "page_id": {
            "type": "string",
            "title": "页面 ID（add_comment 时使用）",
        },
    },
    "required": ["base_url", "email", "api_token", "space_key"],
}


class ConfluencePlugin(BasePlugin):
    """调用 Confluence REST API 发布页面 / 评论。"""

    def __init__(self):
        self.id = "confluence"
        self.name = "Confluence 集成"
        self.description = "通过 Confluence REST API 创建页面或给页面添加评论。"
        self.category = "integration"
        self.version = "1.0.0"
        self.config_schema = CONFLUENCE_CONFIG_SCHEMA

    async def execute(self, context: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        base = str(config.get("base_url", "")).rstrip("/")
        email = config.get("email")
        token = config.get("api_token")
        space = config.get("space_key")
        if not (base and email and token and space):
            return {"ok": False, "error": "缺少配置 base_url/email/api_token/space_key"}

        auth = httpx.BasicAuth(email, token)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        action = config.get("action", "create_page")
        body_text = context.get("message") or json.dumps(context, ensure_ascii=False, default=str)
        # 简单转义尖括号，避免破坏 storage 格式 XML
        safe_body = str(body_text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        try:
            async with httpx.AsyncClient(timeout=10, auth=auth) as client:
                if action == "create_page":
                    title = context.get("title") or f"[AI-PM] {context.get('event', '事件')}"
                    payload: Dict[str, Any] = {
                        "type": "page",
                        "title": title,
                        "space": {"key": space},
                        "body": {
                            "storage": {
                                "value": f"<p>{safe_body}</p>",
                                "representation": "storage",
                            }
                        },
                    }
                    if config.get("parent_id"):
                        payload["ancestors"] = [{"id": str(config["parent_id"])}]
                    resp = await client.post(
                        f"{base}{CONFLUENCE_API_PATH}", json=payload, headers=headers
                    )
                    data = resp.json()
                    return {
                        "ok": resp.status_code < 400,
                        "status_code": resp.status_code,
                        "page_id": data.get("id"),
                        "url": (data.get("_links") or {}).get("web"),
                    }
                elif action == "add_comment":
                    page_id = config.get("page_id") or context.get("page_id")
                    if not page_id:
                        return {"ok": False, "error": "缺少 page_id"}
                    payload = {
                        "type": "comment",
                        "container": {"id": str(page_id), "type": "page"},
                        "body": {
                            "storage": {
                                "value": f"<p>{safe_body}</p>",
                                "representation": "storage",
                            }
                        },
                    }
                    resp = await client.post(
                        f"{base}{CONFLUENCE_API_PATH}", json=payload, headers=headers
                    )
                    data = resp.json()
                    return {
                        "ok": resp.status_code < 400,
                        "status_code": resp.status_code,
                        "id": data.get("id"),
                    }
                else:
                    return {"ok": False, "error": f"不支持的 action: {action}"}
        except Exception as e:
            logger.exception("Confluence 插件调用失败")
            return {"ok": False, "error": str(e)}


register_plugin(ConfluencePlugin())

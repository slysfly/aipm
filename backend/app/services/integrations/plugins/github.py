"""
官方插件：GitHub 集成

调用 GitHub REST API（使用 Personal Access Token）：
- create_issue：在指定仓库创建 Issue
- add_label：给指定 Issue 打标签
"""

import json
import logging
from typing import Dict, Any, Optional

import httpx

from app.services.integrations.plugin_sdk import BasePlugin, register_plugin

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

GITHUB_CONFIG_SCHEMA = {
    "type": "object",
    "title": "GitHub 插件配置",
    "properties": {
        "token": {
            "type": "string",
            "title": "Personal Access Token",
            "description": "需具备 repo 权限",
        },
        "owner": {"type": "string", "title": "仓库所有者（组织/用户）"},
        "repo": {"type": "string", "title": "仓库名"},
        "action": {
            "type": "string",
            "enum": ["create_issue", "add_label"],
            "default": "create_issue",
            "title": "执行动作",
        },
        "label": {
            "type": "string",
            "title": "标签（add_label 时使用）",
        },
    },
    "required": ["token", "owner", "repo"],
}


class GitHubPlugin(BasePlugin):
    """调用 GitHub REST API 创建 Issue / 打标签。"""

    def __init__(self):
        self.id = "github"
        self.name = "GitHub 集成"
        self.description = "通过 GitHub REST API 创建 Issue 或给 Issue 打标签。"
        self.category = "integration"
        self.version = "1.0.0"
        self.config_schema = GITHUB_CONFIG_SCHEMA

    async def execute(self, context: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        token = config.get("token")
        owner = config.get("owner")
        repo = config.get("repo")
        if not (token and owner and repo):
            return {"ok": False, "error": "缺少配置 token/owner/repo"}

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        action = config.get("action", "create_issue")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if action == "create_issue":
                    title = context.get("title") or f"[AI-PM] {context.get('event', '事件')}"
                    body = context.get("message") or json.dumps(
                        context, ensure_ascii=False, default=str
                    )
                    resp = await client.post(
                        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
                        json={"title": title, "body": body},
                        headers=headers,
                    )
                    data = resp.json()
                    return {
                        "ok": resp.status_code < 400,
                        "status_code": resp.status_code,
                        "issue_url": data.get("html_url"),
                    }
                elif action == "add_label":
                    label = config.get("label") or context.get("label")
                    if not label:
                        return {"ok": False, "error": "缺少 label"}
                    number = context.get("issue_number") or config.get("issue_number")
                    if number is None:
                        return {"ok": False, "error": "缺少 issue_number"}
                    resp = await client.post(
                        f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{number}/labels",
                        json=[label],
                        headers=headers,
                    )
                    return {"ok": resp.status_code < 400, "status_code": resp.status_code}
                else:
                    return {"ok": False, "error": f"不支持的 action: {action}"}
        except Exception as e:
            logger.exception("GitHub 插件调用失败")
            return {"ok": False, "error": str(e)}


register_plugin(GitHubPlugin())

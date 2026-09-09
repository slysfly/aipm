"""
官方插件：Jenkins 集成

触发 Jenkins Job 构建：
- 若配置了构建参数（params），使用 /job/{job}/buildWithParameters
- 否则使用 /job/{job}/build
- 支持可选的远程构建令牌（token 参数）与 Basic 认证
"""

import logging
from typing import Dict, Any, Optional

import httpx

from app.services.integrations.plugin_sdk import BasePlugin, register_plugin

logger = logging.getLogger(__name__)

JENKINS_CONFIG_SCHEMA = {
    "type": "object",
    "title": "Jenkins 插件配置",
    "properties": {
        "base_url": {
            "type": "string",
            "format": "uri",
            "title": "Jenkins 地址",
            "description": "例如 https://jenkins.example.com",
        },
        "user": {"type": "string", "title": "用户名（可选）"},
        "api_token": {"type": "string", "title": "API Token（与 user 配套）"},
        "job_name": {"type": "string", "title": "任务名称（Job）"},
        "build_token": {
            "type": "string",
            "title": "构建令牌（可选）",
            "description": "对应 Job 的 'Trigger builds remotely' 令牌",
        },
        "params": {
            "type": "object",
            "title": "构建参数（可选）",
            "description": "键值对，将作为构建参数传递",
        },
    },
    "required": ["base_url", "job_name"],
}


class JenkinsPlugin(BasePlugin):
    """触发 Jenkins Job 构建。"""

    def __init__(self):
        self.id = "jenkins"
        self.name = "Jenkins 集成"
        self.description = "触发 Jenkins Job 构建（支持构建参数与远程令牌）。"
        self.category = "automation"
        self.version = "1.0.0"
        self.config_schema = JENKINS_CONFIG_SCHEMA

    async def execute(self, context: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        base = str(config.get("base_url", "")).rstrip("/")
        job = config.get("job_name")
        if not (base and job):
            return {"ok": False, "error": "缺少配置 base_url/job_name"}

        # Basic 认证（可选）
        auth: Optional[httpx.Auth] = None
        if config.get("user") and config.get("api_token"):
            auth = httpx.BasicAuth(str(config["user"]), str(config["api_token"]))

        # 构建参数：远程令牌 + 用户自定义参数（context 中的构建参数也会并入）
        params: Dict[str, Any] = {}
        if config.get("build_token"):
            params["token"] = config["build_token"]
        for k, v in (config.get("params") or {}).items():
            params[str(k)] = v
        for k, v in (context.get("params") or {}).items():
            params[str(k)] = v

        # 有参数走 buildWithParameters，否则走 build
        path = "/job/%s/buildWithParameters" % job if params else "/job/%s/build" % job

        try:
            async with httpx.AsyncClient(timeout=10, auth=auth) as client:
                resp = await client.post(f"{base}{path}", params=params)
            # Jenkins 成功排队通常返回 201
            ok = resp.status_code in (200, 201)
            return {
                "ok": ok,
                "status_code": resp.status_code,
                "queued": ok,
            }
        except Exception as e:
            logger.exception("Jenkins 插件调用失败")
            return {"ok": False, "error": str(e)}


register_plugin(JenkinsPlugin())

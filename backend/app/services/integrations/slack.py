import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.models.integration import Integration
from app.core.exceptions import BusinessException
from app.services.integrations.base import is_mock, exchange_oauth_code, api_get, api_post, require_real


SLACK_OAUTH_URL = "https://slack.com/oauth/v2/authorize"
SLACK_API_BASE = "https://slack.com/api"


class SlackService:
    def __init__(self, client_id: str = None, client_secret: str = None):
        self.client_id = client_id or "mock_slack_client_id"
        self.client_secret = client_secret or "mock_slack_client_secret"

    def get_oauth_url(self, redirect_uri: str, state: str = "", scopes: Optional[List[str]] = None) -> str:
        default_scopes = ["chat:write", "commands", "users:read", "channels:read", "im:read", "groups:read"]
        params = {"client_id": self.client_id, "scope": ",".join(scopes or default_scopes), "redirect_uri": redirect_uri, "state": state}
        import urllib.parse
        query = urllib.parse.urlencode(params)
        return f"{SLACK_OAUTH_URL}?{query}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        return await exchange_oauth_code("https://slack.com/api/oauth.v2.access", self.client_id, self.client_secret, code, "")

    async def get_user_info(self, access_token: str, user_id: str) -> Dict[str, Any]:
        require_real(access_token, user_id)
        data = await api_get(f"{SLACK_API_BASE}/users.info", access_token, params={"user": user_id})
        if not data.get("ok"):
            raise BusinessException(f"Slack 获取用户信息失败: {data.get('error')}")
        u = data["user"]
        return {
            "id": u.get("id"),
            "name": u.get("name"),
            "real_name": (u.get("profile") or {}).get("real_name"),
            "email": (u.get("profile") or {}).get("email"),
            "team_id": u.get("team_id"),
        }

    async def send_message(self, access_token: str, channel: str, text: str, blocks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        require_real(access_token, channel)
        payload = {"channel": channel, "text": text}
        if blocks:
            payload["blocks"] = blocks
        return await api_post(f"{SLACK_API_BASE}/chat.postMessage", access_token, json=payload)

    async def send_rich_message(self, access_token: str, channel: str, blocks: List[Dict[str, Any]], text: str = "") -> Dict[str, Any]:
        return await self.send_message(access_token, channel, text, blocks=blocks)

    async def list_channels(self, access_token: str, limit: int = 50) -> List[Dict[str, Any]]:
        require_real(access_token)
        data = await api_get(f"{SLACK_API_BASE}/conversations.list", access_token, params={"limit": limit, "types": "public_channel,private_channel"})
        if not data.get("ok"):
            raise BusinessException(f"Slack 获取频道失败: {data.get('error')}")
        return data.get("channels", [])

    async def list_users(self, access_token: str, limit: int = 50) -> List[Dict[str, Any]]:
        require_real(access_token)
        data = await api_get(f"{SLACK_API_BASE}/users.list", access_token, params={"limit": limit})
        if not data.get("ok"):
            raise BusinessException(f"Slack 获取成员失败: {data.get('error')}")
        return data.get("members", [])

    async def handle_slash_command(self, command: str, text: str, user_id: str, channel_id: str) -> Dict[str, Any]:
        if command == "/create-task":
            parts = text.split("|") if "|" in text else [text, ""]
            task_name = parts[0].strip()
            assignee = parts[1].strip() if len(parts) > 1 else user_id
            return {"response_type": "in_channel", "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": f"*新任务已创建*\n• 名称: {task_name}\n• 负责人: <@{assignee}>\n• 创建人: <@{user_id}>"}}]}
        return {"text": f"未知命令: {command}"}

    async def verify_request_signature(self, signing_secret: str, timestamp: str, body: str, signature: str) -> bool:
        basestring = f"v0:{timestamp}:{body}"
        expected = "v0=" + hmac.new(signing_secret.encode("utf-8"), basestring.encode("utf-8"), digestmod=hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


class SlackWebhookHandler:
    def __init__(self, signing_secret: str = "mock_slack_signing_secret"):
        self.signing_secret = signing_secret
        self.slack_service = SlackService()

    async def verify_request(self, timestamp: str, body: str, signature: str) -> bool:
        return await self.slack_service.verify_request_signature(self.signing_secret, timestamp, body, signature)

    async def handle_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event_type = payload.get("type", "")
        if event_type == "url_verification":
            return {"challenge": payload.get("challenge", "")}
        elif event_type == "event_callback":
            inner = payload.get("event", {})
            inner_type = inner.get("type", "")
            if inner_type == "message" and not inner.get("bot_id"):
                return {"action": "process_message", "channel": inner.get("channel"), "text": inner.get("text")}
            elif inner_type == "app_mention":
                return {"action": "reply_mention", "channel": inner.get("channel")}
        elif payload.get("command"):
            return await self.slack_service.handle_slash_command(payload["command"], payload.get("text", ""), payload.get("user_id", ""), payload.get("channel_id", ""))
        return {"action": "ack"}

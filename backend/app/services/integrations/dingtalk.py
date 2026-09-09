import hmac
import hashlib
import base64
import urllib.parse
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.models.integration import Integration
from app.core.exceptions import BusinessException
from app.services.integrations.base import is_mock, exchange_oauth_code, api_get, api_post, require_real
from app.config import settings


DINGTALK_OAUTH_URL = "https://oapi.dingtalk.com/connect/oauth2/sns_authorize"
DINGTALK_API_BASE = "https://oapi.dingtalk.com"


class DingTalkService:
    def __init__(self, app_key: str = None, app_secret: str = None):
        self.app_key = app_key or settings.DINGTALK_APP_KEY or "mock_dingtalk_app_key"
        self.app_secret = app_secret or settings.DINGTALK_APP_SECRET or "mock_dingtalk_app_secret"

    def get_oauth_url(self, redirect_uri: str, state: str = "") -> str:
        params = {"appid": self.app_key, "response_type": "code", "scope": "snsapi_auth", "redirect_uri": redirect_uri, "state": state}
        query = urllib.parse.urlencode(params)
        return f"{DINGTALK_OAUTH_URL}?{query}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        return await exchange_oauth_code(
            "https://oapi.dingtalk.com/topapi/v2/user/getuserinfo",
            self.app_key, self.app_secret, code, "",
        )

    async def get_app_token(self) -> str:
        """用应用凭证换取 access_token（审批等开放接口需要）"""
        require_real(self.app_key, self.app_secret)
        data = await api_get(f"{DINGTALK_API_BASE}/gettoken", "", params={"appkey": self.app_key, "appsecret": self.app_secret})
        if data.get("errcode") != 0:
            raise BusinessException(f"获取钉钉 access_token 失败: {data.get('errmsg')}")
        return data["access_token"]

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        require_real(refresh_token)
        return {"access_token": f"dingtalk_access_refreshed_{int(time.time())}", "refresh_token": refresh_token, "expires_in": 7200}

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        require_real(access_token)
        # 用 user access_token 换取用户详情
        data = await api_post(f"{DINGTALK_API_BASE}/topapi/v2/user/get", access_token, json={"userid": ""})
        # 简化：直接返回基本信息（sns 场景需额外换 userid）
        return {"name": "钉钉用户", "avatar": "https://static.dingtalk.com/media/avatar.png"}

    async def send_group_message(self, access_token: str, chat_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        require_real(access_token)
        return await api_post(f"{DINGTALK_API_BASE}/topapi/message/send", access_token, json={
            "msg": message, "chatid": chat_id,
        })

    async def send_text_to_group(self, access_token: str, chat_id: str, text: str) -> Dict[str, Any]:
        return await self.send_group_message(access_token, chat_id, {"msgtype": "text", "text": {"content": text}})

    async def send_markdown_to_group(self, access_token: str, chat_id: str, title: str, text: str) -> Dict[str, Any]:
        return await self.send_group_message(access_token, chat_id, {"msgtype": "markdown", "markdown": {"title": title, "text": text}})

    def generate_webhook_sign(self, timestamp: str, secret: str) -> str:
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        return urllib.parse.quote_plus(base64.b64encode(hmac_code))

    async def send_webhook_message(self, webhook_url: str, secret: str, message: Dict[str, Any]) -> Dict[str, Any]:
        require_real(webhook_url)
        import httpx
        timestamp = str(int(time.time() * 1000))
        sign = self.generate_webhook_sign(timestamp, secret)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook_url, json={**message, "timestamp": timestamp, "sign": sign})
        return resp.json()


class DingTalkWebhookHandler:
    def __init__(self, secret: str = "mock_webhook_secret"):
        self.secret = secret

    def verify_signature(self, timestamp: str, sign: str) -> bool:
        expected = DingTalkService().generate_webhook_sign(timestamp, self.secret)
        return hmac.compare_digest(expected, sign)

    async def handle_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event_type = payload.get("msgtype") or payload.get("EventType", "unknown")
        if event_type == "text":
            return {"reply": f"收到消息: {payload.get('text', {}).get('content', '')}"}
        return {"action": "ack"}

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


WECOM_OAUTH_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
WECOM_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


class WeComService:
    def __init__(self, corp_id: str = None, corp_secret: str = None, agent_id: str = None):
        self.corp_id = corp_id or settings.WECOM_CORP_ID or "mock_wecom_corp_id"
        self.corp_secret = corp_secret or settings.WECOM_CORP_SECRET or "mock_wecom_corp_secret"
        self.agent_id = agent_id or settings.WECOM_AGENT_ID or "mock_agent_id"

    def get_oauth_url(self, redirect_uri: str, state: str = "") -> str:
        params = {"appid": self.corp_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": "snsapi_base", "state": state}
        query = urllib.parse.urlencode(params)
        return f"{WECOM_OAUTH_URL}?{query}#wechat_redirect"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        return await exchange_oauth_code(f"{WECOM_API_BASE}/auth/getuserinfo", self.corp_id, self.corp_secret, code, "")

    async def get_access_token(self) -> str:
        """用企业凭证换取 access_token（通讯录/应用消息等接口需要）"""
        require_real(self.corp_id, self.corp_secret)
        data = await api_get(f"{WECOM_API_BASE}/gettoken", "", params={"corpid": self.corp_id, "corpsecret": self.corp_secret})
        if data.get("errcode") != 0:
            raise BusinessException(f"获取企业微信 access_token 失败: {data.get('errmsg')}")
        return data["access_token"]

    async def get_user_info(self, access_token: str, userid: str) -> Dict[str, Any]:
        require_real(access_token, userid)
        data = await api_get(f"{WECOM_API_BASE}/user/get", access_token, params={"userid": userid})
        return {
            "userid": data.get("userid"),
            "name": data.get("name"),
            "avatar": data.get("avatar"),
            "mobile": data.get("mobile"),
            "email": data.get("email"),
            "department": data.get("department"),
            "position": data.get("position"),
            "gender": data.get("gender"),
            "status": data.get("status"),
        }

    async def send_message(self, access_token: str, user_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        require_real(access_token, user_id)
        return await api_post(f"{WECOM_API_BASE}/message/send", access_token, json={**message, "touser": user_id, "agentid": int(self.agent_id) if str(self.agent_id).isdigit() else self.agent_id})

    async def send_text_message(self, access_token: str, user_id: str, text: str) -> Dict[str, Any]:
        return await self.send_message(access_token, user_id, {"msgtype": "text", "text": {"content": text}})

    async def send_markdown_message(self, access_token: str, user_id: str, content: str) -> Dict[str, Any]:
        return await self.send_message(access_token, user_id, {"msgtype": "markdown", "markdown": {"content": content}})

    async def send_to_chat(self, access_token: str, chat_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        require_real(access_token, chat_id)
        return await api_post(f"{WECOM_API_BASE}/appchat/send", access_token, json={"chatid": chat_id, **message})

    def generate_webhook_sign(self, secret: str) -> str:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        sign = base64.b64encode(hmac_code).decode("utf-8")
        return f"&timestamp={timestamp}&sign={urllib.parse.quote(sign)}"

    async def send_webhook_message(self, webhook_key: str, secret: str, message: Dict[str, Any]) -> Dict[str, Any]:
        require_real(webhook_key)
        import httpx
        sign = self.generate_webhook_sign(secret)
        url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}{sign}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=message)
        return resp.json()

    async def get_department_list(self, access_token: str) -> List[Dict[str, Any]]:
        require_real(access_token)
        data = await api_get(f"{WECOM_API_BASE}/department/list", access_token, params={"id": 0})
        return data.get("department", [])

    async def get_department_members(self, access_token: str, department_id: int) -> List[Dict[str, Any]]:
        require_real(access_token)
        data = await api_get(f"{WECOM_API_BASE}/user/simplelist", access_token, params={"department_id": department_id, "fetch_child": 0})
        return data.get("userlist", [])


class WeComWebhookHandler:
    def __init__(self, token: str = "mock_wecom_token", encoding_aes_key: str = "mock_encoding_aes_key"):
        self.token = token
        self.encoding_aes_key = encoding_aes_key

    def verify_signature(self, signature: str, timestamp: str, nonce: str, msg_encrypt: str = "") -> bool:
        tmp_list = [self.token, timestamp, nonce, msg_encrypt]
        tmp_list.sort()
        tmp_str = "".join(tmp_list)
        hashcode = hashlib.sha1(tmp_str.encode()).hexdigest()
        return hashcode == signature

    async def handle_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event_type = payload.get("MsgType") or payload.get("Event", "unknown")
        if event_type == "text":
            return {"reply": f"收到: {payload.get('Content', '')}"}
        elif event_type == "click":
            return {"action": "menu_click", "event_key": payload.get("EventKey")}
        return {"action": "ack"}

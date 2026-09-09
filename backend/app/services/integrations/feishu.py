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


FEISHU_OAUTH_URL = "https://open.feishu.cn/open-apis/authen/v1/index"
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


class FeishuService:
    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or settings.FEISHU_APP_ID or "mock_feishu_app_id"
        self.app_secret = app_secret or settings.FEISHU_APP_SECRET or "mock_feishu_app_secret"

    def get_oauth_url(self, redirect_uri: str, state: str = "") -> str:
        params = {
            "app_id": self.app_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        query = urllib.parse.urlencode(params)
        return f"{FEISHU_OAUTH_URL}?{query}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        return await exchange_oauth_code(
            "https://open.feishu.cn/open-apis/authen/v1/access_token",
            self.app_id, self.app_secret, code, "",
            extra={"grant_type": "authorization_code"},
        )

    async def get_tenant_access_token(self) -> str:
        """用应用凭证换取 tenant_access_token（多维表格/审批等开放接口需要）"""
        require_real(self.app_id, self.app_secret)
        data = await api_post(
            f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        if data.get("code") != 0:
            raise BusinessException(f"获取飞书 tenant_token 失败: {data.get('msg')}")
        return data["tenant_access_token"]

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        require_real(self.app_id, self.app_secret, refresh_token)
        data = await api_post(
            f"{FEISHU_API_BASE}/authen/v1/refresh_access_token",
            json={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        return {
            "access_token": data.get("access_token", ""),
            "refresh_token": data.get("refresh_token", ""),
            "expires_in": data.get("expires_in", 7200),
        }

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        require_real(access_token)
        data = await api_get(f"{FEISHU_API_BASE}/authen/v1/user_info", access_token)
        return {
            "open_id": data.get("open_id"),
            "union_id": data.get("union_id"),
            "name": data.get("name", "飞书用户"),
            "avatar": data.get("avatar") or data.get("avatar_url"),
            "mobile": data.get("mobile"),
            "email": data.get("email"),
            "employee_type": data.get("employee_type"),
            "job_title": data.get("job_title"),
        }

    async def send_chat_message(self, access_token: str, chat_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        require_real(access_token)
        return await api_post(
            f"{FEISHU_API_BASE}/im/v1/messages",
            access_token,
            json={"receive_id": chat_id, "msg_type": message.get("msg_type"), "content": _json_str(message.get("content", {}))},
            params={"receive_id_type": "chat_id"},
        )

    async def send_text_to_chat(self, access_token: str, chat_id: str, text: str) -> Dict[str, Any]:
        return await self.send_chat_message(access_token, chat_id, {"msg_type": "text", "content": {"text": text}})

    async def send_rich_text_to_chat(self, access_token: str, chat_id: str, title: str, content: List[Dict[str, Any]]) -> Dict[str, Any]:
        return await self.send_chat_message(
            access_token, chat_id,
            {"msg_type": "post", "content": {"post": {"zh_cn": {"title": title, "content": content}}}},
        )

    def generate_webhook_sign(self, timestamp: str, secret: str) -> str:
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    async def send_webhook_message(self, webhook_url: str, secret: str, message: Dict[str, Any]) -> Dict[str, Any]:
        require_real(webhook_url)
        timestamp = str(int(time.time()))
        sign = self.generate_webhook_sign(timestamp, secret)
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(webhook_url, json={**message, "timestamp": timestamp, "sign": sign})
        return resp.json()

    async def get_bitable_records(self, app_token: str, table_id: str, page_size: int = 50) -> List[Dict[str, Any]]:
        """
        真实拉取飞书多维表格记录（用 tenant_access_token）。
        字段映射：任务名称/负责人/状态/截止日期/优先级。
        """
        require_real(self.app_id, self.app_secret, app_token, table_id)
        token = await self.get_tenant_access_token()
        records = []
        page_token = None
        while True:
            params = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            data = await api_get(
                f"{FEISHU_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                token, params=params,
            )
            items = data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else data.get("items", [])
            records.extend(items)
            page_token = (data.get("data", {}) or {}).get("page_token") or data.get("page_token")
            if not page_token or len(items) < page_size:
                break
        return records

    async def sync_bitable_to_tasks(self, access_token: str, app_token: str, table_id: str, project_id: str) -> Dict[str, Any]:
        raw = await self.get_bitable_records(app_token, table_id)
        tasks = []
        for record in raw:
            fields = record.get("fields", {})
            status_map = {"待处理": "todo", "进行中": "in_progress", "已完成": "done"}
            tasks.append({
                "id": f"task_{record.get('record_id')}",
                "name": fields.get("任务名称", "未命名任务"),
                "status": status_map.get(fields.get("状态"), "todo"),
                "assignee": fields.get("负责人", ""),
                "source": "feishu_bitable",
                "source_id": record.get("record_id"),
                "due_date": _as_date(fields.get("截止日期")),
                "priority": _priority_from_label(fields.get("优先级")),
            })
        return {"synced_count": len(tasks), "tasks": tasks}

    async def _require_real(self, *values):
        require_real(*values)


class FeishuWebhookHandler:
    def __init__(self, secret: str = "mock_feishu_webhook_secret"):
        self.secret = secret

    def verify_signature(self, timestamp: str, sign: str) -> bool:
        expected = FeishuService().generate_webhook_sign(timestamp, self.secret)
        return hmac.compare_digest(expected, sign)

    async def handle_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event_type = payload.get("header", {}).get("event_type", "unknown")
        if event_type == "im.message.receive_v1":
            return {"action": "reply_message", "message_id": payload.get("event", {}).get("message", {}).get("message_id")}
        elif event_type == "bitable.record.changed_v1":
            return {"action": "sync_bitable", "record_id": payload.get("event", {}).get("record_id")}
        return {"action": "ack"}


def _json_str(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


def _as_date(v) -> Optional[str]:
    if not v:
        return None
    if isinstance(v, list):
        v = v[0] if v else None
    return str(v)[:10] if v else None


def _priority_from_label(label) -> int:
    mapping = {"高": 2, "中": 3, "低": 4, "紧急": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}
    if isinstance(label, list):
        label = label[0] if label else ""
    return mapping.get(str(label), 3)

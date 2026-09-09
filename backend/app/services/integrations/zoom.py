import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.models.integration import Integration
from app.core.exceptions import BusinessException
from app.services.integrations.base import is_mock, exchange_oauth_code, api_get, api_post, require_real


ZOOM_OAUTH_URL = "https://zoom.us/oauth/authorize"
ZOOM_API_BASE = "https://api.zoom.us/v2"


class ZoomService:
    def __init__(self, client_id: str = None, client_secret: str = None):
        self.client_id = client_id or "mock_zoom_client_id"
        self.client_secret = client_secret or "mock_zoom_client_secret"

    def get_oauth_url(self, redirect_uri: str, state: str = "") -> str:
        params = {"client_id": self.client_id, "response_type": "code", "redirect_uri": redirect_uri, "state": state}
        import urllib.parse
        query = urllib.parse.urlencode(params)
        return f"{ZOOM_OAUTH_URL}?{query}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        return await exchange_oauth_code("https://zoom.us/oauth/token", self.client_id, self.client_secret, code, "")

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        require_real(refresh_token)
        return {"access_token": f"zoom_access_refreshed_{int(time.time())}", "refresh_token": refresh_token, "expires_in": 3600, "token_type": "bearer"}

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        require_real(access_token)
        return await api_get(f"{ZOOM_API_BASE}/users/me", access_token)

    async def create_meeting(self, access_token: str, topic: str, start_time: str, duration: int = 60, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        require_real(access_token, topic)
        return await api_post(f"{ZOOM_API_BASE}/users/me/meetings", access_token, json={
            "topic": topic, "start_time": start_time, "duration": duration, "timezone": "Asia/Shanghai", "settings": settings or {},
        })

    async def list_meetings(self, access_token: str, type_: str = "scheduled", page_size: int = 30) -> List[Dict[str, Any]]:
        require_real(access_token)
        data = await api_get(f"{ZOOM_API_BASE}/users/me/meetings", access_token, params={"type": type_, "page_size": page_size})
        return data.get("meetings", [])

    async def get_meeting(self, access_token: str, meeting_id: int) -> Dict[str, Any]:
        require_real(access_token)
        return await api_get(f"{ZOOM_API_BASE}/meetings/{meeting_id}", access_token)

    async def delete_meeting(self, access_token: str, meeting_id: int) -> Dict[str, Any]:
        require_real(access_token)
        await api_post(f"{ZOOM_API_BASE}/meetings/{meeting_id}/status", access_token, json={"action": "end"})
        return {"success": True, "meeting_id": meeting_id}

    async def list_recordings(self, access_token: str, from_date: str, to_date: str) -> List[Dict[str, Any]]:
        require_real(access_token)
        data = await api_get(f"{ZOOM_API_BASE}/users/me/recordings", access_token, params={"from": from_date, "to": to_date, "page_size": 30})
        return data.get("meetings", [])

    async def sync_recordings(self, access_token: str, project_id: str) -> Dict[str, Any]:
        now = datetime.now()
        from_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        to_date = now.strftime("%Y-%m-%d")
        recordings = await self.list_recordings(access_token, from_date, to_date)
        attachments = []
        for rec in recordings:
            for file in rec.get("recording_files", []):
                attachments.append({
                    "id": f"att_{file.get('id')}",
                    "name": f"{rec.get('topic')}.{file.get('file_type', '').lower()}",
                    "mime_type": f"video/{file.get('file_type', '').lower()}" if file.get("file_type") == "MP4" else f"audio/{file.get('file_type', '').lower()}",
                    "source": "zoom_recording",
                    "source_id": file.get("id"),
                    "url": file.get("download_url"),
                    "size": file.get("file_size"),
                })
        return {"synced_count": len(attachments), "attachments": attachments}


class ZoomWebhookHandler:
    def __init__(self, secret: str = "mock_zoom_webhook_secret"):
        self.secret = secret

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        expected = hmac.new(self.secret.encode("utf-8"), payload, digestmod=hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        event_type = payload.get("event", "")
        if event_type == "meeting.started":
            return {"action": "meeting_started", "meeting_id": payload.get("payload", {}).get("object", {}).get("id")}
        elif event_type == "meeting.ended":
            return {"action": "meeting_ended", "meeting_id": payload.get("payload", {}).get("object", {}).get("id")}
        elif event_type == "recording.completed":
            return {"action": "recording_ready", "recording": payload.get("payload", {}).get("object", {})}
        elif event_type == "endpoint.url_validation":
            plain_token = payload.get("payload", {}).get("plainToken", "")
            encrypted_token = hmac.new(self.secret.encode("utf-8"), plain_token.encode("utf-8"), digestmod=hashlib.sha256).hexdigest()
            return {"plainToken": plain_token, "encryptedToken": encrypted_token}
        return {"action": "ack"}

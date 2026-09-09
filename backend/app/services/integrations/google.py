import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.models.integration import Integration
from app.core.exceptions import BusinessException
from app.services.integrations.base import is_mock, exchange_oauth_code, api_get, api_post, require_real


GOOGLE_OAUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_API_BASE = "https://www.googleapis.com"


class GoogleService:
    def __init__(self, client_id: str = None, client_secret: str = None):
        self.client_id = client_id or "mock_google_client_id"
        self.client_secret = client_secret or "mock_google_client_secret"

    def get_oauth_url(self, redirect_uri: str, state: str = "", scope: Optional[str] = None) -> str:
        default_scope = "openid email profile https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/spreadsheets"
        params = {"client_id": self.client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": scope or default_scope, "access_type": "offline", "prompt": "consent", "state": state}
        import urllib.parse
        query = urllib.parse.urlencode(params)
        return f"{GOOGLE_OAUTH_URL}?{query}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        return await exchange_oauth_code(GOOGLE_TOKEN_URL, self.client_id, self.client_secret, code, "")

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        require_real(refresh_token)
        return {"access_token": f"google_access_refreshed_{int(time.time())}", "expires_in": 3600, "token_type": "Bearer"}

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        require_real(access_token)
        return await api_get("https://openidconnect.googleapis.com/v1/userinfo", access_token)

    async def list_calendar_events(self, access_token: str, calendar_id: str = "primary", time_min: Optional[str] = None, time_max: Optional[str] = None) -> List[Dict[str, Any]]:
        require_real(access_token)
        params = {"maxResults": 50, "orderBy": "startTime", "singleEvents": True}
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        data = await api_get(f"{GOOGLE_API_BASE}/calendar/v3/calendars/{calendar_id}/events", access_token, params=params)
        return data.get("items", [])

    async def create_calendar_event(self, access_token: str, event: Dict[str, Any], calendar_id: str = "primary") -> Dict[str, Any]:
        require_real(access_token)
        return await api_post(f"{GOOGLE_API_BASE}/calendar/v3/calendars/{calendar_id}/events", access_token, json=event)

    async def sync_calendar_to_tasks(self, access_token: str, project_id: str) -> Dict[str, Any]:
        events = await self.list_calendar_events(access_token)
        tasks = []
        for event in events:
            start = (event.get("start") or {}).get("dateTime") or event.get("start", {}).get("date")
            end = (event.get("end") or {}).get("dateTime") or event.get("end", {}).get("date")
            tasks.append({
                "id": f"task_{event.get('id')}",
                "name": event.get("summary", "未命名日程"),
                "status": "todo",
                "source": "google_calendar",
                "source_id": event.get("id"),
                "start_time": start,
                "end_time": end,
                "url": event.get("htmlLink"),
            })
        return {"synced_count": len(tasks), "tasks": tasks}

    async def list_drive_files(self, access_token: str, query: Optional[str] = None) -> List[Dict[str, Any]]:
        require_real(access_token)
        params = {"pageSize": 50, "fields": "files(id,name,mimeType,createdTime,modifiedTime,webViewLink,size)"}
        if query:
            params["q"] = query
        data = await api_get(f"{GOOGLE_API_BASE}/drive/v3/files", access_token, params=params)
        return data.get("files", [])

    async def sync_drive_files(self, access_token: str, project_id: str) -> Dict[str, Any]:
        files = await self.list_drive_files(access_token)
        attachments = []
        for file in files:
            attachments.append({
                "id": f"att_{file.get('id')}",
                "name": file.get("name"),
                "mime_type": file.get("mimeType"),
                "source": "google_drive",
                "source_id": file.get("id"),
                "url": file.get("webViewLink"),
            })
        return {"synced_count": len(attachments), "attachments": attachments}

    async def create_spreadsheet(self, access_token: str, title: str) -> Dict[str, Any]:
        require_real(access_token)
        return await api_post(f"{GOOGLE_API_BASE}/v4/spreadsheets", access_token, json={"properties": {"title": title}})

    async def export_tasks_to_sheet(self, access_token: str, spreadsheet_id: str, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        require_real(access_token, spreadsheet_id)
        headers = ["ID", "任务名称", "状态", "负责人", "截止日期", "优先级"]
        rows = [headers]
        for task in tasks:
            rows.append([task.get("id", ""), task.get("name", ""), task.get("status", ""), task.get("assignee", ""), task.get("due_date", ""), task.get("priority", "")])
        return await api_post(
            f"{GOOGLE_API_BASE}/v4/spreadsheets/{spreadsheet_id}/values/Sheet1!A1:append",
            access_token,
            json={"values": rows, "majorDimension": "ROWS"},
            params={"valueInputOption": "USER_ENTERED"},
        )

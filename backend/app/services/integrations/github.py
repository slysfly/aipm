import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from app.models.integration import Integration
from app.core.exceptions import BusinessException
from app.services.integrations.base import is_mock, exchange_oauth_code, api_get, api_post, require_real


GITHUB_OAUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_API_BASE = "https://api.github.com"


class GitHubService:
    def __init__(self, client_id: str = None, client_secret: str = None):
        self.client_id = client_id or "mock_github_client_id"
        self.client_secret = client_secret or "mock_github_client_secret"

    def get_oauth_url(self, redirect_uri: str, state: str = "", scope: Optional[str] = None) -> str:
        default_scope = "repo,user,read:org,write:discussion"
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": scope or default_scope,
            "state": state,
        }
        import urllib.parse
        query = urllib.parse.urlencode(params)
        return f"{GITHUB_OAUTH_URL}?{query}"

    async def exchange_code(self, code: str) -> Dict[str, Any]:
        return await exchange_oauth_code(
            "https://github.com/login/oauth/access_token",
            self.client_id, self.client_secret, code, "",
            extra={"accept": "json"},
        )

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        require_real(access_token)
        data = await api_get(f"{GITHUB_API_BASE}/user", access_token)
        return {
            "login": data.get("login"),
            "id": data.get("id"),
            "avatar_url": data.get("avatar_url"),
            "html_url": data.get("html_url"),
            "name": data.get("name"),
            "email": data.get("email"),
            "bio": data.get("bio"),
            "public_repos": data.get("public_repos"),
            "followers": data.get("followers"),
            "following": data.get("following"),
        }

    async def list_repositories(self, access_token: str, page: int = 1, per_page: int = 30) -> List[Dict[str, Any]]:
        require_real(access_token)
        return await api_get(f"{GITHUB_API_BASE}/user/repos", access_token, params={"page": page, "per_page": per_page})

    async def list_issues(self, access_token: str, owner: str, repo: str, state: str = "open") -> List[Dict[str, Any]]:
        require_real(access_token, owner, repo)
        return await api_get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues", access_token, params={"state": state, "per_page": 50})

    async def sync_issues_to_tasks(self, access_token: str, owner: str, repo: str, project_id: str) -> Dict[str, Any]:
        issues = await self.list_issues(access_token, owner, repo)
        # GitHub 的 issues 接口会包含 PR，过滤掉
        issues = [i for i in issues if "pull_request" not in i]
        tasks = []
        for issue in issues:
            tasks.append({
                "id": f"task_gh_{issue['id']}",
                "name": issue.get("title", "未命名"),
                "status": "in_progress" if issue.get("state") == "open" else "done",
                "source": "github_issue",
                "source_id": str(issue.get("number")),
                "description": issue.get("body"),
                "assignee": (issue.get("assignee") or {}).get("login"),
                "url": issue.get("html_url"),
                "due_date": (issue.get("closed_at") or "")[:10],
            })
        return {"synced_count": len(tasks), "tasks": tasks}

    async def list_pull_requests(self, access_token: str, owner: str, repo: str, state: str = "open") -> List[Dict[str, Any]]:
        require_real(access_token, owner, repo)
        return await api_get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls", access_token, params={"state": state, "per_page": 50})

    async def sync_pr_status(self, access_token: str, owner: str, repo: str) -> Dict[str, Any]:
        prs = await self.list_pull_requests(access_token, owner, repo)
        return {
            "total": len(prs),
            "open": len([p for p in prs if p.get("state") == "open"]),
            "merged": len([p for p in prs if p.get("merged")]),
            "draft": len([p for p in prs if p.get("draft")]),
            "prs": prs,
        }

    async def create_webhook(self, access_token: str, owner: str, repo: str, config: Dict[str, Any]) -> Dict[str, Any]:
        require_real(access_token, owner, repo)
        return await api_post(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/hooks", access_token, json={
            "name": "web",
            "active": True,
            "events": config.get("events", ["push", "pull_request", "issues"]),
            "config": config,
        })


class GitHubWebhookHandler:
    def __init__(self, secret: str = "mock_github_webhook_secret"):
        self.secret = secret

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        expected = "sha256=" + hmac.new(self.secret.encode("utf-8"), payload, digestmod=hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def handle_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if event_type == "push":
            return {"action": "sync_commits", "repository": payload.get("repository", {}).get("full_name"), "ref": payload.get("ref"), "commits": len(payload.get("commits", []))}
        elif event_type == "pull_request":
            return {"action": "sync_pr", "repository": payload.get("repository", {}).get("full_name"), "pr_number": payload.get("pull_request", {}).get("number"), "pr_action": payload.get("action")}
        elif event_type == "issues":
            return {"action": "sync_issue", "repository": payload.get("repository", {}).get("full_name"), "issue_number": payload.get("issue", {}).get("number"), "issue_action": payload.get("action")}
        return {"action": "ack", "event_type": event_type}

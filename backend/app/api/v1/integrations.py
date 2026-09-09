"""
[PMBOK KA: 采购管理 | PG: 执行 (Procurement/Executing) — 外部工具集成]
对应PMI第6版标准：外部集成、供应商对接

[CPMAI Phase: CPMAI Phase: Data Understanding | Domain: Data for AI — 数据源集成]"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import time
import hmac
import secrets
import logging

logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User, Task, Project, TaskStatus, TaskPriority
from app.models.integration import Integration
from app.services.integrations.dingtalk import DingTalkService, DingTalkWebhookHandler
from app.services.integrations.feishu import FeishuService, FeishuWebhookHandler
from app.services.integrations.wecom import WeComService, WeComWebhookHandler
from app.services.integrations.google import GoogleService
from app.services.integrations.slack import SlackService, SlackWebhookHandler
from app.services.integrations.github import GitHubService, GitHubWebhookHandler
from app.services.integrations.zoom import ZoomService, ZoomWebhookHandler

router = APIRouter(prefix="/integrations", tags=["集成管理"])

PROVIDERS = {
    "dingtalk": {
        "name": "钉钉",
        "description": "钉钉消息通知、审批同步、机器人Webhook",
        "icon": "dingtalk",
        "category": "im",
        "features": ["OAuth登录", "消息推送", "审批同步", "Webhook"],
    },
    "feishu": {
        "name": "飞书",
        "description": "飞书消息通知、多维表格同步、机器人Webhook",
        "icon": "feishu",
        "category": "im",
        "features": ["OAuth登录", "消息推送", "多维表格", "Webhook"],
    },
    "wecom": {
        "name": "企业微信",
        "description": "企业微信消息通知、通讯录同步、机器人Webhook",
        "icon": "wecom",
        "category": "im",
        "features": ["OAuth登录", "消息推送", "通讯录", "Webhook"],
    },
    "google": {
        "name": "Google",
        "description": "Google Calendar同步、Drive文件同步、Sheets导出",
        "icon": "google",
        "category": "productivity",
        "features": ["OAuth登录", "日历同步", "文件同步", "表格导出"],
    },
    "slack": {
        "name": "Slack",
        "description": "Slack消息通知、Slash命令、机器人集成",
        "icon": "slack",
        "category": "im",
        "features": ["OAuth登录", "消息推送", "Slash命令", "机器人"],
    },
    "github": {
        "name": "GitHub",
        "description": "GitHub仓库同步、Issue转任务、PR状态同步、Webhook",
        "icon": "github",
        "category": "dev",
        "features": ["OAuth登录", "仓库列表", "Issue同步", "PR同步", "Webhook"],
    },
    "zoom": {
        "name": "Zoom",
        "description": "Zoom会议创建、会议列表、录制同步",
        "icon": "zoom",
        "category": "meeting",
        "features": ["OAuth登录", "创建会议", "会议列表", "录制同步"],
    },
}


def get_service(provider: str):
    from app.config import settings
    if provider == "dingtalk":
        return DingTalkService()
    elif provider == "feishu":
        return FeishuService()
    elif provider == "wecom":
        return WeComService()
    elif provider == "google":
        return GoogleService()
    elif provider == "slack":
        return SlackService()
    elif provider == "github":
        return GitHubService()
    elif provider == "zoom":
        return ZoomService()
    raise HTTPException(status_code=400, detail=f"不支持的集成提供商: {provider}")


# ============== 扫码直连（设备授权码模式） ==============
# 演示用：进程内存储扫码会话；生产环境可替换为 Redis 等共享存储。
SCAN_SESSIONS: Dict[str, Dict[str, Any]] = {}
SCAN_TTL = 300  # 秒


def _build_app_creds(provider: str, user_id: str) -> Dict[str, Any]:
    """为「自动创建应用」场景合成应用凭证（演示 / 沙箱用）。

    真实环境应改为调用对应开放平台「创建应用」接口（如飞书应用管理、钉钉微应用
    创建、企业微信自建应用创建等），并把平台返回的真实 app_id/app_secret 落库。
    """
    seeded = f"{provider}-{user_id}"
    app_id = f"aipm_auto_{provider}_{abs(hash(seeded)) % 10 ** 10:010d}"
    app_secret = secrets.token_hex(16)
    return {"app_id": app_id, "app_secret": app_secret}


async def _auto_link_or_create(
    db: AsyncSession,
    provider: str,
    user: User,
    *,
    access_token: str = "",
    refresh_token: str = "",
    expires_in: int = 3600,
    app_name: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> "tuple[Integration, str]":
    """扫码 / 授权完成后统一处理「关联已有 or 自动创建应用」。

    返回 (integration, mode)，mode ∈ {"linked", "created"}。

    - 已存在该提供商的集成记录  -> 直接关联（复用既有应用凭证），mode="linked"
    - 不存在                    -> 由对应系统自动创建应用并落库，mode="created"
    """
    config = config or {}
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == user.id,
            Integration.provider == provider,
        )
    )
    existing = result.scalar_one_or_none()

    expires_at = datetime.now() + timedelta(seconds=expires_in)

    if existing:
        # 已有应用 -> 直接关联（复用既有应用凭证）
        existing.access_token = access_token or existing.access_token
        existing.refresh_token = refresh_token or existing.refresh_token
        existing.expires_at = expires_at
        existing.status = "connected"
        merged = dict(existing.config or {})
        merged.update(config)
        merged["app_mode"] = "linked"
        merged["linked_at"] = datetime.now().isoformat()
        existing.config = merged
        await db.commit()
        await db.refresh(existing)
        return existing, "linked"

    # 没有应用 -> 由对应系统自动创建（此处合成应用凭证并落库）
    creds = _build_app_creds(provider, user.id)
    integration = Integration(
        user_id=user.id,
        provider=provider,
        access_token=access_token or f"mock_token_{secrets.token_hex(8)}",
        refresh_token=refresh_token or f"mock_refresh_{secrets.token_hex(8)}",
        expires_at=expires_at,
        status="connected",
        config={
            **config,
            "app_id": creds["app_id"],
            "app_secret": creds["app_secret"],
            "app_name": app_name or f"{PROVIDERS[provider]['name']} 自建应用",
            "app_mode": "created",
            "created_at": datetime.now().isoformat(),
        },
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return integration, "created"


_STATUS_MAP = {
    "todo": TaskStatus.TODO.value,
    "in_progress": TaskStatus.IN_PROGRESS.value,
    "done": TaskStatus.DONE.value,
    "completed": TaskStatus.DONE.value,
}


async def _persist_synced_tasks(db, project_id: str, provider: str, tasks: List[Dict[str, Any]]) -> int:
    """将同步得到的任务落库（双向同步闭环）：
    - 以 (project_id, source, source_id) 去重，已存在则更新，不存在则新建。
    - 来源信息写入 labels（如 sync:github_issue:123），便于追溯与反向清理。
    """
    if not project_id or not tasks:
        return 0

    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not proj:
        return 0

    # 载入本项目已有任务，按 label 在 Python 层去重（兼容 SQLite / PostgreSQL）
    existing_rows = (await db.execute(select(Task).where(Task.project_id == project_id))).scalars().all()
    existing_by_label = {}
    for row in existing_rows:
        for lb in (row.labels or []):
            existing_by_label[lb] = row

    created = 0
    for t in tasks:
        source = t.get("source") or provider
        source_id = str(t.get("source_id") or t.get("id") or "")
        label = f"sync:{source}:{source_id}"
        existing = existing_by_label.get(label)

        if existing:
            existing.name = t.get("name", existing.name)
            existing.status = _STATUS_MAP.get(t.get("status"), existing.status)
            existing.description = t.get("description") or existing.description
            existing.updated_at = datetime.now()
        else:
            db.add(Task(
                project_id=project_id,
                name=t.get("name", "未命名同步任务"),
                description=t.get("description"),
                status=_STATUS_MAP.get(t.get("status"), TaskStatus.TODO.value),
                priority=t.get("priority") or TaskPriority.MEDIUM.value,
                wbs_code=f"EXT-{source}-{source_id}"[:50],
                labels=[label, source],
                category=f"集成同步/{provider}",
                planned_end=_parse_date(t.get("due_date") or t.get("end_time")),
                planned_start=_parse_date(t.get("start_time")),
                is_milestone=False,
            ))
            created += 1
    await db.commit()
    return created


def _parse_date(v) -> Optional[datetime]:
    if not v:
        return None
    s = str(v)[:19].replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


@router.get("/", response_model=Dict[str, Any])
async def list_integrations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Integration).where(Integration.user_id == current_user.id)
    )
    integrations = result.scalars().all()

    connected = {i.provider: i for i in integrations}

    items = []
    for key, meta in PROVIDERS.items():
        inst = connected.get(key)
        items.append({
            "provider": key,
            "name": meta["name"],
            "description": meta["description"],
            "icon": meta["icon"],
            "category": meta["category"],
            "features": meta["features"],
            "status": inst.status if inst else "disconnected",
            "connected_at": inst.created_at.isoformat() if inst else None,
            "app_mode": (inst.config or {}).get("app_mode") if inst else None,
            "app_name": (inst.config or {}).get("app_name") if inst else None,
            "config": inst.config if inst else {},
        })

    return {"success": True, "data": items}


@router.get("/{provider}/oauth-url")
async def get_oauth_url(
    provider: str,
    redirect_uri: str,
    current_user: User = Depends(get_current_user),
):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="不支持的提供商")

    service = get_service(provider)
    state = f"{provider}:{current_user.id}:{int(time.time())}"
    url = service.get_oauth_url(redirect_uri=redirect_uri, state=state)
    return {"success": True, "data": {"oauth_url": url, "state": state}}


@router.post("/{provider}/scan-login")
async def scan_login(
    provider: str,
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    """生成扫码直连会话：返回二维码内容（前端回调 URL）与轮询 token。

    手机扫码后打开 qr_content 指向的前端页面，前端检测到 scan 参数即自动调用
    scan-confirm 完成「关联已有 / 自动创建应用」并连通。
    """
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="不支持的提供商")

    token = secrets.token_urlsafe(24)
    SCAN_SESSIONS[token] = {
        "provider": provider,
        "user_id": current_user.id,
        "status": "pending",
        "created_at": time.time(),
    }

    # 二维码内容：手机扫码后打开此 URL，前端读取 scan 参数自动完成确认
    origin = (request.headers.get("origin") if request else None) or ""
    qr_content = f"{origin}/integrations?scan=1&token={token}&provider={provider}"
    return {
        "success": True,
        "data": {
            "token": token,
            "qr_content": qr_content,
            "expires_in": SCAN_TTL,
            "provider": provider,
        },
    }


@router.get("/{provider}/scan-status")
async def scan_status(
    provider: str,
    token: str,
    current_user: User = Depends(get_current_user),
):
    sess = SCAN_SESSIONS.get(token)
    if not sess or sess.get("provider") != provider:
        raise HTTPException(status_code=404, detail="扫码会话不存在或已失效")

    if sess["status"] == "confirmed":
        return {
            "success": True,
            "data": {
                "status": "confirmed",
                "provider": provider,
                "app_mode": sess.get("app_mode"),
                "app_name": sess.get("app_name"),
            },
        }
    # 演示态：若会话已超时则提示重新发起
    if time.time() - sess.get("created_at", 0) > SCAN_TTL:
        raise HTTPException(status_code=410, detail="扫码二维码已过期，请重新发起")
    return {"success": True, "data": {"status": sess["status"], "provider": provider}}


@router.post("/{provider}/scan-confirm")
async def scan_confirm(
    provider: str,
    token: str,
    payload: Optional[Dict[str, Any]] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """完成扫码（演示「模拟扫码」或手机扫码后前端回调触发）。

    统一执行「关联已有 / 自动创建应用」并把集成置为已连通。
    """
    sess = SCAN_SESSIONS.get(token)
    if not sess or sess.get("provider") != provider:
        raise HTTPException(status_code=404, detail="扫码会话不存在或已失效")
    if sess["status"] == "confirmed":
        raise HTTPException(status_code=400, detail="该扫码会话已完成")

    # 锁定为会话所属用户，避免越权关联
    target_user_id = sess["user_id"]
    if current_user.id != target_user_id:
        user = (await db.execute(select(User).where(User.id == target_user_id))).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=403, detail="扫码会话用户不匹配")
    else:
        user = current_user

    config = (payload or {}).get("config", {})
    integration, mode = await _auto_link_or_create(
        db, provider, user,
        app_name=(payload or {}).get("app_name", ""),
        config=config,
    )

    sess["status"] = "confirmed"
    sess["app_mode"] = mode
    sess["app_name"] = (integration.config or {}).get("app_name")

    return {
        "success": True,
        "data": {
            "provider": provider,
            "status": "connected",
            "app_mode": mode,
            "app_name": (integration.config or {}).get("app_name"),
            "app_id": (integration.config or {}).get("app_id"),
        },
    }


@router.post("/{provider}/connect")
async def connect_integration(
    provider: str,
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="不支持的提供商")

    code = payload.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="缺少授权码")

    service = get_service(provider)
    token_data = await service.exchange_code(code)

    # 统一处理「关联已有 / 自动创建应用」
    integration, mode = await _auto_link_or_create(
        db, provider, current_user,
        access_token=token_data.get("access_token", ""),
        refresh_token=token_data.get("refresh_token", ""),
        expires_in=token_data.get("expires_in", 3600),
        config=payload.get("config", {}),
    )

    user_info = {}
    try:
        if provider == "wecom":
            user_info = await service.get_user_info(token_data.get("access_token", ""), token_data.get("userid", ""))
        else:
            user_info = await service.get_user_info(token_data.get("access_token", ""))
    except Exception as e:
        logger.warning("获取第三方用户信息失败（已忽略）: %s", e, exc_info=True)

    return {
        "success": True,
        "data": {
            "provider": provider,
            "status": "connected",
            "app_mode": mode,
            "user_info": user_info,
        },
    }


@router.post("/{provider}/disconnect")
async def disconnect_integration(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == current_user.id,
            Integration.provider == provider,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.status = "disconnected"
        existing.access_token = None
        existing.refresh_token = None
        await db.commit()

    return {"success": True, "data": {"provider": provider, "status": "disconnected"}}


@router.get("/{provider}/status")
async def get_integration_status(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == current_user.id,
            Integration.provider == provider,
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        return {"success": True, "data": {"provider": provider, "status": "disconnected"}}

    is_expired = integration.expires_at and integration.expires_at < datetime.now()
    status = integration.status
    if is_expired and status == "connected":
        status = "expired"

    return {
        "success": True,
        "data": {
            "provider": provider,
            "status": status,
            "connected_at": integration.created_at.isoformat() if integration.created_at else None,
            "expires_at": integration.expires_at.isoformat() if integration.expires_at else None,
            "config": integration.config,
        },
    }


@router.post("/{provider}/sync")
async def sync_integration(
    provider: str,
    payload: Optional[Dict[str, Any]] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == current_user.id,
            Integration.provider == provider,
            Integration.status == "connected",
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=400, detail="集成未连接")

    service = get_service(provider)
    sync_type = (payload or {}).get("sync_type", "default")
    project_id = (payload or {}).get("project_id", "")

    sync_result = {}

    if provider == "dingtalk":
        sync_result = {"message": "钉钉同步完成", "items": []}
    elif provider == "feishu":
        if sync_type == "bitable":
            config = integration.config or {}
            sync_result = await service.sync_bitable_to_tasks(
                integration.access_token,
                config.get("app_token", ""),
                config.get("table_id", ""),
                project_id,
            )
        else:
            sync_result = {"message": "飞书同步完成", "items": []}
    elif provider == "google":
        if sync_type == "calendar":
            sync_result = await service.sync_calendar_to_tasks(integration.access_token, project_id)
        elif sync_type == "drive":
            sync_result = await service.sync_drive_files(integration.access_token, project_id)
        else:
            sync_result = {"message": "Google同步完成", "items": []}
    elif provider == "github":
        config = integration.config or {}
        owner = config.get("owner", "")
        repo = config.get("repo", "")
        if sync_type == "issues":
            sync_result = await service.sync_issues_to_tasks(integration.access_token, owner, repo, project_id)
        elif sync_type == "prs":
            sync_result = await service.sync_pr_status(integration.access_token, owner, repo)
        else:
            sync_result = {"message": "GitHub同步完成", "items": []}
    elif provider == "zoom":
        if sync_type == "recordings":
            sync_result = await service.sync_recordings(integration.access_token, project_id)
        else:
            sync_result = {"message": "Zoom同步完成", "items": []}
    else:
        sync_result = {"message": "同步完成", "items": []}

    # 将同步得到的任务落库，实现「外部平台 → 本系统」双向同步闭环
    persisted = 0
    if isinstance(sync_result, dict) and sync_result.get("tasks"):
        persisted = await _persist_synced_tasks(db, project_id, provider, sync_result["tasks"])

    sync_result["persisted"] = persisted
    return {"success": True, "data": {"provider": provider, "sync_type": sync_type, "result": sync_result}}


@router.post("/{provider}/webhook")
async def receive_webhook(
    provider: str,
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_slack_signature: Optional[str] = Header(None),
    x_slack_request_timestamp: Optional[str] = Header(None),
    x_zoom_signature: Optional[str] = Header(None),
):
    body = await request.body()
    payload = await request.json()

    if provider == "github":
        event_type = request.headers.get("X-GitHub-Event", "")
        handler = GitHubWebhookHandler()
        if not x_hub_signature_256 or not handler.verify_signature(body, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="签名验证失败")
        result = await handler.handle_event(event_type, payload)
    elif provider == "slack":
        handler = SlackWebhookHandler()
        if not x_slack_signature or not x_slack_request_timestamp or not await handler.verify_request(x_slack_request_timestamp, body.decode(), x_slack_signature):
            raise HTTPException(status_code=401, detail="签名验证失败")
        result = await handler.handle_event(payload)
    elif provider == "dingtalk":
        timestamp = payload.get("timestamp", "")
        sign = payload.get("sign", "")
        handler = DingTalkWebhookHandler()
        if not sign or not handler.verify_signature(timestamp, sign):
            raise HTTPException(status_code=401, detail="签名验证失败")
        result = await handler.handle_event(payload)
    elif provider == "feishu":
        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        sign = request.headers.get("X-Lark-Signature", "")
        handler = FeishuWebhookHandler()
        if not sign or not handler.verify_signature(timestamp, sign):
            raise HTTPException(status_code=401, detail="签名验证失败")
        result = await handler.handle_event(payload)
    elif provider == "wecom":
        signature = request.query_params.get("signature", "")
        timestamp = request.query_params.get("timestamp", "")
        nonce = request.query_params.get("nonce", "")
        handler = WeComWebhookHandler()
        if not handler.verify_signature(signature, timestamp, nonce):
            raise HTTPException(status_code=401, detail="签名验证失败")
        result = await handler.handle_event(payload)
    elif provider == "zoom":
        handler = ZoomWebhookHandler()
        if not x_zoom_signature or not handler.verify_signature(body, x_zoom_signature):
            raise HTTPException(status_code=401, detail="签名验证失败")
        result = await handler.handle_event(payload)
    else:
        result = {"action": "ack"}

    return {"success": True, "data": result}


@router.post("/{provider}/action/{action}")
async def integration_action(
    provider: str,
    action: str,
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == current_user.id,
            Integration.provider == provider,
            Integration.status == "connected",
        )
    )
    integration = result.scalar_one_or_none()

    if not integration:
        raise HTTPException(status_code=400, detail="集成未连接")

    service = get_service(provider)
    action_result = {}

    if provider == "dingtalk":
        if action == "send_message":
            action_result = await service.send_text_to_group(
                integration.access_token,
                payload.get("chat_id", ""),
                payload.get("text", ""),
            )
        elif action == "send_markdown":
            action_result = await service.send_markdown_to_group(
                integration.access_token,
                payload.get("chat_id", ""),
                payload.get("title", ""),
                payload.get("text", ""),
            )
    elif provider == "feishu":
        if action == "send_message":
            action_result = await service.send_text_to_chat(
                integration.access_token,
                payload.get("chat_id", ""),
                payload.get("text", ""),
            )
    elif provider == "wecom":
        if action == "send_message":
            action_result = await service.send_text_message(
                integration.access_token,
                payload.get("user_id", ""),
                payload.get("text", ""),
            )
    elif provider == "google":
        if action == "create_event":
            action_result = await service.create_calendar_event(
                integration.access_token,
                payload.get("event", {}),
            )
        elif action == "create_sheet":
            action_result = await service.create_spreadsheet(
                integration.access_token,
                payload.get("title", "导出数据"),
            )
    elif provider == "slack":
        if action == "send_message":
            action_result = await service.send_message(
                integration.access_token,
                payload.get("channel", ""),
                payload.get("text", ""),
            )
    elif provider == "github":
        if action == "list_repos":
            action_result = await service.list_repositories(integration.access_token)
        elif action == "list_issues":
            action_result = await service.list_issues(
                integration.access_token,
                payload.get("owner", ""),
                payload.get("repo", ""),
            )
        elif action == "list_prs":
            action_result = await service.list_pull_requests(
                integration.access_token,
                payload.get("owner", ""),
                payload.get("repo", ""),
            )
    elif provider == "zoom":
        if action == "create_meeting":
            action_result = await service.create_meeting(
                integration.access_token,
                payload.get("topic", ""),
                payload.get("start_time", ""),
                payload.get("duration", 60),
            )
        elif action == "list_meetings":
            action_result = await service.list_meetings(integration.access_token)

    return {"success": True, "data": {"provider": provider, "action": action, "result": action_result}}


# ============== 入站 -> Agent 桥接（连接器触发 Agent） ==============

class InboundAgentRequest(BaseModel):
    provider: str = "dingtalk"   # 来源平台：dingtalk/feishu/github/...
    project_id: str
    content: str                 # 文本（会议纪要 / 需求文档 / Issue 正文）


@router.post("/inbound/agent")
async def inbound_to_agent(
    payload: InboundAgentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """连接器桥接：钉钉/飞书机器人、GitHub Webhook 等可将文本推送到本端点，
    由「纪要转任务 Agent」自动解析并创建任务（壁垒 C：连接器 + Agent 闭环）。
    """
    from app.services.ai.out_of_box_agents import run_agent
    try:
        result = await run_agent(
            "meeting_minutes", db, current_user.id,
            payload.project_id, payload.content, {"create": True},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "provider": payload.provider, "result": result}

"""
IM Gateway API — 多平台即时通讯接入网关
[PMBOK KA: 沟通管理 | PG: 执行 — 外部沟通渠道集成]

核心能力：
1. 平台配置管理（App ID/Secret）
2. 用户IM绑定（用户隔离，不串台）
3. 消息入站处理（Webhook → AI → 响应）
4. 自然语言指令执行（查询/创建/更新/删除）
5. 冲突检测与提示
6. 完整审计日志
"""

import time
import os
import re
import signal
import json
import hmac
import hashlib
import logging
import asyncio
import urllib.request
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.im_gateway import (
    IMProviderConfig, UserIMBinding, IMConversationSession, IMAuditLog,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/im-gateway", tags=["IM网关"])

# ============================================================
# 平台元数据
# ============================================================
PLATFORM_META = {
    "dingtalk": {
        "name": "钉钉",
        "icon": "dingtalk",
        "color": "#0089FF",
        "description": "钉钉机器人 / Webhook / 消息卡片",
        "fields": [
            {"key": "app_id", "label": "App ID", "placeholder": "钉钉应用的 AppKey", "required": True},
            {"key": "app_secret", "label": "App Secret", "placeholder": "钉钉应用的 AppSecret", "required": True, "secret": True},
            {"key": "verification_token", "label": "Token", "placeholder": "机器人 Token（可选）"},
        ],
        "capabilities": ["chat", "command", "notification"],
    },
    "feishu": {
        "name": "飞书",
        "icon": "feishu",
        "color": "#3370FF",
        "description": "飞书机器人 / 事件订阅 / 消息卡片",
        "fields": [
            {"key": "app_id", "label": "App ID", "placeholder": "飞书应用的 App ID", "required": True},
            {"key": "app_secret", "label": "App Secret", "placeholder": "飞书应用的 App Secret", "required": True, "secret": True},
            {"key": "encrypt_key", "label": "Encrypt Key", "placeholder": "事件加密密钥（可选）"},
            {"key": "verification_token", "label": "Verification Token", "placeholder": "事件验证令牌（可选）"},
        ],
        "capabilities": ["chat", "command", "notification", "wiki"],
    },
    "wecom": {
        "name": "企业微信",
        "icon": "wecom",
        "color": "#2DC100",
        "description": "企业微信机器人 / 回调模式 / 应用消息",
        "fields": [
            {"key": "app_id", "label": "CorpID", "placeholder": "企业ID", "required": True},
            {"key": "app_secret", "label": "Secret", "placeholder": "应用 Secret", "required": True, "secret": True},
            {"key": "verification_token", "label": "Token", "placeholder": "回调 URL 的 Token"},
            {"key": "encrypt_key", "label": "EncodingAESKey", "placeholder": "消息加解密密钥"},
        ],
        "capabilities": ["chat", "command", "notification"],
    },
    "slack": {
        "name": "Slack",
        "icon": "slack",
        "color": "#4A154B",
        "description": "Slack Bot / Slash Commands / Interactive Components",
        "fields": [
            {"key": "app_id", "label": "Bot Token", "placeholder": "xoxb-...", "required": True},
            {"key": "app_secret", "label": "Signing Secret", "placeholder": "签名密钥", "required": True, "secret": True},
            {"key": "verification_token", "label": "Verification Token", "placeholder": "验证令牌（可选）"},
        ],
        "capabilities": ["chat", "command", "notification"],
    },
}


# ============================================================
# Schemas
# ============================================================
class ProviderConfigCreate(BaseModel):
    provider: str = Field(..., description="平台标识: dingtalk/feishu/wecom/slack")
    app_id: str = Field(..., description="App ID / AppKey")
    app_secret: str = Field(..., description="App Secret")
    verification_token: Optional[str] = None
    encrypt_key: Optional[str] = None
    capabilities: Optional[List[str]] = None


class ProviderConfigUpdate(BaseModel):
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    verification_token: Optional[str] = None
    encrypt_key: Optional[str] = None
    enabled: Optional[bool] = None
    capabilities: Optional[List[str]] = None


class UserBindingCreate(BaseModel):
    provider: str
    im_user_id: str
    im_user_name: Optional[str] = None
    im_tenant_id: Optional[str] = None
    default_project_id: Optional[str] = None


class IMMessageInbound(BaseModel):
    """入站消息：由各平台Webhook回调推送"""
    provider: str
    event_type: str = "message"          # message / event / callback
    im_user_id: str                      # 发送者IM用户ID
    im_chat_id: Optional[str] = None     # 会话ID（群聊/私聊）
    message_type: str = "text"           # text / markdown / interactive / post
    content: str                         # 消息文本内容
    message_id: Optional[str] = None     # 消息唯一ID（防重放）
    timestamp: Optional[int] = None      # 消息时间戳


class IMCommandResult(BaseModel):
    """指令执行结果"""
    success: bool
    reply_text: str                     # 返回给用户的文本
    reply_type: str = "text"            # text / markdown / card / action_card
    actions_taken: List[Dict[str, Any]] = []  # 执行的操作列表
    conflict_alerts: List[Dict[str, Any]] = [] # 冲突警告
    session_id: Optional[str] = None


# ============================================================
# 1. 平台配置管理（管理员）
# ============================================================
@router.get("/providers")
async def list_providers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出所有平台配置状态（扁平化字段，前端直接可用）"""
    result = await db.execute(select(IMProviderConfig))
    configs = {c.provider: c for c in result.scalars().all()}

    providers = []
    for key, meta in PLATFORM_META.items():
        cfg = configs.get(key)
        item: Dict[str, Any] = {
            "provider": key,
            "name": meta["name"],
            "icon": meta.get("icon", key),
            "color": meta.get("color"),
            "description": meta["description"],
            "configured": cfg is not None,
            "enabled": cfg.enabled if cfg else False,
        }
        if cfg:
            # 扁平化：前端直接读 app_id / app_secret_display / webhook_url
            cd = cfg.to_dict()
            item["app_id"] = cfg.app_id or ""
            item["app_secret_display"] = cd.get("appSecret", "****")
            item["webhook_url"] = cfg.webhook_url or ""
            item["capabilities"] = cd.get("capabilities", [])
        providers.append(item)
    return {"data": providers}


@router.post("/providers")
async def create_provider_config(
    payload: ProviderConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建平台配置（需管理员权限）"""
    if payload.provider not in PLATFORM_META:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {payload.provider}")

    existing = await db.execute(
        select(IMProviderConfig).where(IMProviderConfig.provider == payload.provider)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"平台 {payload.provider} 已配置")

    meta = PLATFORM_META[payload.provider]
    config = IMProviderConfig(
        provider=payload.provider,
        provider_name=meta["name"],
        category=meta.get("category", "im"),
        app_id=payload.app_id,
        app_secret=payload.app_secret,
        verification_token=payload.verification_token,
        encrypt_key=payload.encrypt_key,
        capabilities=payload.capabilities or meta.get("capabilities", []),
        created_by=current_user.id,
        enabled=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return {"success": True, "data": config.to_dict()}


@router.put("/providers/{provider}")
async def update_provider_config(
    provider: str,
    payload: ProviderConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新平台配置（upsert：无记录时自动创建）"""
    if provider not in PLATFORM_META:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {provider}")

    result = await db.execute(
        select(IMProviderConfig).where(IMProviderConfig.provider == provider)
    )
    config = result.scalar_one_or_none()

    update_data = payload.model_dump(exclude_unset=True)
    if config:
        # 已有记录 → 更新
        for field, value in update_data.items():
            setattr(config, field, value)
        # 保存凭证时自动启用
        if not config.enabled and (config.app_id or config.app_secret):
            config.enabled = True
    else:
        # 无记录 → 自动创建（upsert）
        meta = PLATFORM_META[provider]
        config = IMProviderConfig(
            provider=provider,
            provider_name=meta["name"],
            enabled=True,
            **update_data,
        )
        db.add(config)
    await db.commit()
    await db.refresh(config)
    return {"success": True, "data": config.to_dict()}


@router.delete("/providers/{provider}")
async def delete_provider_config(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除平台配置（同时清理所有用户绑定）"""
    result = await db.execute(
        select(IMProviderConfig).where(IMProviderConfig.provider == provider)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="平台未配置")

    # 清理绑定
    await db.execute(delete(UserIMBinding).where(UserIMBinding.provider == provider))
    await db.delete(config)
    await db.commit()
    return {"success": True}


# ============================================================
# 2. 用户绑定管理
# ============================================================
@router.get("/bindings")
async def list_my_bindings(
    provider: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查看当前用户的IM绑定"""
    query = select(UserIMBinding).where(UserIMBinding.user_id == current_user.id)
    if provider:
        query = query.where(UserIMBinding.provider == provider)
    result = await db.execute(query)
    bindings = [b.to_dict() for b in result.scalars().all()]
    return {"data": bindings}


@router.post("/bindings")
async def create_binding(
    payload: UserBindingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建IM账号绑定"""
    if payload.provider not in PLATFORM_META:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {payload.provider}")

    # 检查是否已绑定
    existing = await db.execute(
        select(UserIMBinding).where(
            UserIMBinding.user_id == current_user.id,
            UserIMBinding.provider == payload.provider,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该平台已绑定")

    # 检查IM用户是否已被其他人绑定
    im_existing = await db.execute(
        select(UserIMBinding).where(
            UserIMBinding.provider == payload.provider,
            UserIMBinding.im_user_id == payload.im_user_id,
        )
    )
    if im_existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该IM账号已被其他用户绑定（严格隔离原则）")

    binding = UserIMBinding(
        user_id=current_user.id,
        provider=payload.provider,
        im_user_id=payload.im_user_id,
        im_user_name=payload.im_user_name,
        im_tenant_id=payload.im_tenant_id,
        default_project_id=payload.default_project_id,
        status="active",
    )
    db.add(binding)
    await db.commit()
    await db.refresh(binding)
    return {"success": True, "data": binding.to_dict()}


@router.delete("/bindings/{binding_id}")
async def remove_binding(
    binding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """解绑IM账号"""
    result = await db.execute(
        select(UserIMBinding).where(
            UserIMBinding.id == binding_id,
            UserIMBinding.user_id == current_user.id,
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="绑定不存在")
    binding.status = "revoked"
    await db.commit()
    return {"success": True}


# ============================================================
# 3. 消息入站处理（Webhook → AI → 响应）
# ============================================================
@router.post("/inbound/message")
async def inbound_message(
    payload: IMMessageInbound,
    request: Request,
    x_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    核心端点：接收来自各平台的IM消息，路由到AI处理后返回响应。

    流程：
    1. 验证平台已启用 + 签名校验
    2. 通过 im_user_id 查找用户绑定（用户隔离）
    3. 创建/复用会话 session
    4. 调用 AI 解析意图并执行操作
    5. 冲突检测
    6. 记录审计日志
    7. 返回响应文本
    """
    start_time = time.time()
    source_ip = None
    if request and getattr(request, "client", None):
        source_ip = request.client.host

    # Step 1: 验证平台
    if payload.provider not in PLATFORM_META:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {payload.provider}")

    config_result = await db.execute(
        select(IMProviderConfig).where(
            IMProviderConfig.provider == payload.provider,
            IMProviderConfig.enabled == True,
        )
    )
    config = config_result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=503, detail=f"平台 {payload.provider} 未启用或未配置")

    # TODO: 签名验证（根据各平台规则）

    # Step 2: 查找用户绑定（用户隔离核心）
    binding_result = await db.execute(
        select(UserIMBinding).where(
            UserIMBinding.provider == payload.provider,
            UserIMBinding.im_user_id == payload.im_user_id,
            UserIMBinding.status == "active",
        )
    )
    binding = binding_result.scalar_one_or_none()

    if not binding:
        # 未绑定的用户：自动绑定到管理员账号（首次使用自动开通）
        logger.info(f"IM 用户 {payload.im_user_id}@{payload.provider} 无绑定，尝试自动绑定")
        # 查找系统中的管理员/活跃用户作为默认绑定目标
        admin_result = await db.execute(
            select(User).where(User.is_active == True).limit(1)
        )
        default_user = admin_result.scalar_one_or_none()
        if default_user:
            binding = UserIMBinding(
                user_id=default_user.id,
                provider=payload.provider,
                im_user_id=payload.im_user_id,
                im_user_name=f"IM用户_{payload.im_user_id[:8]}",
                status="active",
            )
            db.add(binding)
            # 立即 flush 以分配 binding.id，供后续会话的 binding_id 外键使用
            await db.flush()
            logger.info(f"已自动绑定 {payload.im_user_id}@{payload.provider} → 用户 {default_user.username}")
        else:
            return IMCommandResult(
                success=True,
                reply_text=(
                    f"您好！欢迎使用PMI中国 AI-PM 智能助手。\n\n"
                    f"系统中暂无可用用户账号，请联系管理员。"
                ),
                reply_type="text",
            ).model_dump()

    user_result = await db.execute(select(User).where(User.id == binding.user_id))
    aipm_user = user_result.scalar_one_or_none()
    if not aipm_user or not aipm_user.is_active:
        return IMCommandResult(
            success=False,
            reply_text="关联的 AIPM 账号不存在或已禁用。",
        ).model_dump()

    # 更新最后活跃时间
    binding.last_active_at = datetime.now()

    # Step 3: 创建/复用会话
    session = await _get_or_create_session(db, binding, payload.im_chat_id)

    # Step 4: AI 处理
    ai_start = time.time()
    try:
        ai_result = await _process_message_with_ai(db, aipm_user, binding, payload.content, session.id)
        ai_ms = (time.time() - ai_start) * 1000
    except Exception as e:
        logger.exception("IM AI processing failed")
        ai_ms = (time.time() - ai_start) * 1000
        ai_result = {
            "reply_text": f"抱歉，处理您的请求时出错了：{str(e)}。请稍后重试或在系统中直接操作。",
            "actions_taken": [],
            "conflict_alerts": [],
            "result_status": "error",
            "error_message": str(e),
        }

    total_ms = (time.time() - start_time) * 1000

    # Step 5: 冲突检测
    conflicts = await _detect_conflicts(db, aipm_user.id, ai_result.get("actions_taken", []))

    # Step 6: 审计日志
    audit_log = IMAuditLog(
        user_id=aipm_user.id,
        provider=payload.provider,
        session_id=session.id,
        action_type="command_exec" if ai_result.get("actions_taken") else "chat_read",
        action_category=ai_result.get("action_category", "query"),
        raw_input=payload.content[:2000],
        parsed_intent=ai_result.get("parsed_intent"),
        executed_action=ai_result.get("actions_taken"),
        result_status=ai_result.get("result_status", ("conflict" if conflicts else "success")),
        result_data={"reply_text": ai_result.get("reply_text", "")[:2000]},
        conflict_details=conflicts if conflicts else None,
        ai_process_ms=ai_ms,
        total_ms=total_ms,
        source_ip=source_ip,
    )
    db.add(audit_log)

    # 更新会话计数
    session.message_count += 1
    session.last_message_at = datetime.now()

    await db.commit()

    # 构建最终响应
    reply_text = ai_result.get("reply_text", "")
    if conflicts:
        conflict_texts = [f"⚠️ {c['description']}" for c in conflicts]
        reply_text = reply_text + "\n\n---\n**冲突提醒**\n" + "\n".join(conflict_texts)

    return IMCommandResult(
        success=True,
        reply_text=reply_text,
        reply_type=ai_result.get("reply_type", "text"),
        actions_taken=ai_result.get("actions_taken", []),
        conflict_alerts=conflicts or [],
        session_id=session.id,
    ).model_dump()


# ============================================================
# 4. 各平台专用 Webhook 入口（透传到统一处理）
# ============================================================
@router.post("/webhook/dingtalk")
async def dingtalk_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """钉钉机器人消息回调"""
    body = await request.json()
    msg = body.get("text", {}).get("content", "") if body.get("msgtype") == "text" else ""
    sender_id = body.get("senderId", "") or body.get("senderStaffId", "") or ""

    if not msg or not sender_id:
        return {"success": False}

    inbound = IMMessageInbound(
        provider="dingtalk",
        event_type="message",
        im_user_id=str(sender_id),
        content=msg.strip(),
        message_id=body.get("msgid"),
        timestamp=int(time.time()),
    )
    result = await inbound_message(inbound, request, db=db)
    # 钉钉需要返回特定格式
    return {
        "msgtype": "text",
        "text": {"content": result["reply_text"]},
    }


@router.post("/webhook/feishu")
async def feishu_webhook(request: Request):
    """飞书事件回调 — 秒级 ACK + 异步处理（避免飞书重试/超时）

    流程：
    1. 飞书 URL 验证（订阅时回显 challenge）
    2. 解析消息，立即返回 200（飞书要求秒级响应，否则会重试）
    3. 后台任务：自动绑定 → 调 OpenClaw 生成回复 → 发回飞书
    """
    try:
        body = await request.json()
    except Exception:
        return {"code": 0}

    # 飞书事件订阅 URL 验证
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    event = body.get("event", {})
    sender = event.get("sender", {})
    message = event.get("message", {})
    chat_id = message.get("chat_id", "")
    content = ""

    if message.get("content"):
        try:
            content_json = json.loads(message["content"])
            content = content_json.get("text", "")
        except Exception:
            content = str(message.get("content", ""))

    # 飞书事件中 sender_id 含 open_id / user_id(工号) / union_id；
    # 回发消息用 receive_id_type=open_id，必须取 open_id
    _sid = sender.get("sender_id") or {}
    sender_id = (
        _sid.get("open_id")
        or _sid.get("user_id")
        or sender.get("open_id", "")
        or sender.get("user_id", "")
    )

    if not content or not sender_id:
        return {"code": 0}

    # 幂等去重：飞书可能重试投递同一消息
    msg_id = message.get("message_id") or f"{sender_id}:{content}"
    if msg_id in _feishu_seen:
        return {"code": 0, "msg": "duplicate"}
    _feishu_seen.add(msg_id)
    if len(_feishu_seen) > 500:
        _feishu_seen.clear()

    # 立即 ACK，后台异步处理（OpenClaw 调用可能耗时数秒）
    asyncio.create_task(_handle_feishu_message(content.strip(), str(sender_id), msg_id, chat_id))
    return {"code": 0, "msg": "accepted"}


# 飞书消息去重集合（进程内，跨重启重置）
_feishu_seen: set = set()


async def _handle_feishu_message(content: str, sender_id: str, msg_id: str, chat_id: str = ""):
    """后台处理飞书消息：绑定用户 → OpenClaw 生成回复 → 发回飞书

    回复目标：群消息(chat_id 以 oc_ 开头)回群里，私聊回用户 open_id。
    """
    # 决定回复目标：群聊回群，私聊回用户
    if chat_id and str(chat_id).startswith("oc_"):
        receive_id = str(chat_id)
        receive_id_type = "chat_id"
    else:
        receive_id = str(sender_id)
        receive_id_type = "open_id"

    # 先发「思考中」占位，避免用户面对长时间静默（OpenClaw 可能需数十秒）
    try:
        await _send_feishu_reply(receive_id, "⏳ 已收到，正在理解并生成回复…", receive_id_type)
    except Exception:
        logger.warning("发送思考中占位失败（可忽略）")

    reply_text = ""
    try:
        from app.db.session import async_session_maker
        async with async_session_maker() as db_sess:
            inbound = IMMessageInbound(
                provider="feishu",
                event_type="message",
                im_user_id=str(sender_id),
                content=content,
                message_id=msg_id,
            )
            # request=None：后台任务中无活动请求对象，inbound_message 已做 source_ip 保护
            result = await inbound_message(inbound, None, db=db_sess)
            reply_text = result.get("reply_text", "")
    except Exception as e:
        logger.exception("Feishu 消息处理失败")
        reply_text = f"抱歉，处理您的消息时出错了：{str(e)}"

    if reply_text:
        try:
            await _send_feishu_reply(receive_id, reply_text, receive_id_type)
        except Exception as e:
            logger.exception("飞书回复发送失败")


@router.post("/webhook/wecom")
async def wecom_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """企业微信回调"""
    body = await request.json()
    # 企业微信 XML/JSON 格式
    from_user = body.get("FromUserName", "")
    content = body.get("Content", "")

    if not content or not from_user:
        return {"code": 0, "msg": "success"}

    inbound = IMMessageInbound(
        provider="wecom",
        event_type="message",
        im_user_id=from_user,
        content=content.strip(),
        message_id=body.get("MsgId"),
    )
    result = await inbound_message(inbound, request, db=db)
    # 企业微信 passive reply
    return {
        "ToUserName": body.get("ToUserName", ""),
        "FromUserName": from_user,
        "CreateTime": int(time.time()),
        "MsgType": "text",
        "Content": result["reply_text"],
    }


# ============================================================
# 5. 会话 & 日志查询
# ============================================================
@router.get("/sessions")
async def list_my_sessions(
    provider: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查看我的IM会话列表"""
    query = select(IMConversationSession).where(
        IMConversationSession.user_id == current_user.id
    ).order_by(IMConversationSession.last_message_at.desc()).limit(limit)
    if provider:
        query = query.where(IMConversationSession.provider == provider)
    result = await db.execute(query)
    sessions = [s.to_dict() for s in result.scalars().all()]
    return {"data": sessions}


@router.get("/audit-logs")
async def list_audit_logs(
    provider: Optional[str] = None,
    action_type: Optional[str] = None,
    result_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询审计日志（管理员可看全部，普通用户只看自己的）"""
    conditions = []
    if not current_user.is_superuser:
        conditions.append(IMAuditLog.user_id == current_user.id)
    if provider:
        conditions.append(IMAuditLog.provider == provider)
    if action_type:
        conditions.append(IMAuditLog.action_type == action_type)
    if result_status:
        conditions.append(IMAuditLog.result_status == result_status)

    query = select(IMAuditLog).where(*conditions) if conditions else select(IMAuditLog)
    query = query.order_by(IMAuditLog.created_at.desc())
    
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = [l.to_dict() for l in result.scalars().all()]

    return {"data": logs, "total": total, "page": page, "pageSize": page_size}


@router.get("/stats")
async def gateway_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """网关统计概览"""
    # 平台配置数
    config_count = (await db.execute(select(func.count()).select_from(IMProviderConfig))).scalar() or 0
    
    # 我的绑定数
    my_bindings = (await db.execute(
        select(func.count()).select_from(UserIMBinding).where(
            UserIMBinding.user_id == current_user.id,
            UserIMBinding.status == "active",
        )
    )).scalar() or 0

    # 总绑定数（管理员可见）
    total_bindings = (await db.execute(
        select(func.count()).select_from(UserIMBinding).where(UserIMBinding.status == "active")
    )).scalar() or 0

    # 今日消息数
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_messages = (await db.execute(
        select(func.count()).select_from(IMAuditLog).where(IMAuditLog.created_at >= today_start)
    )).scalar() or 0

    # 今日冲突数
    today_conflicts = (await db.execute(
        select(func.count()).select_from(IMAuditLog).where(
            IMAuditLog.created_at >= today_start,
            IMAuditLog.result_status == "conflict",
        )
    )).scalar() or 0

    return {
        "configuredPlatforms": config_count,
        "myBindings": my_bindings,
        "totalActiveBindings": total_bindings,
        "todayMessages": today_messages,
        "todayConflicts": today_conflicts,
    }


# ============================================================
# 内部辅助函数
# ============================================================
async def _get_or_create_session(
    db: AsyncSession, binding: UserIMBinding, chat_id: Optional[str]
) -> IMConversationSession:
    """获取或创建会话"""
    if chat_id:
        result = await db.execute(
            select(IMConversationSession).where(
                IMConversationSession.binding_id == binding.id,
                IMConversationSession.im_chat_id == chat_id,
                IMConversationSession.status == "active",
            )
        )
        session = result.scalar_one_or_none()
        if session:
            return session

    session = IMConversationSession(
        binding_id=binding.id,
        user_id=binding.user_id,
        provider=binding.provider,
        im_chat_id=chat_id,
        status="active",
    )
    db.add(session)
    await db.flush()
    return session


async def _process_message_with_ai(
    db: AsyncSession,
    user: User,
    binding: UserIMBinding,
    message: str,
    session_id: str,
) -> Dict[str, Any]:
    """
    AI 消息处理核心：
    1. 调用 AIService.chat() 解析意图
    2. 如果是查询类 → 直接回答
    3. 如果是操作类 → 执行对应操作
    4. 返回结构化结果
    """
    from app.services.ai_service import ai_service

    project_id = binding.default_project_id

    # 构建系统提示：告诉AI它是一个IM助手，可以执行操作
    im_system_prompt = (
        "你是PMI中国 AI-PM 智能项目管理助手。当前用户通过即时通讯工具（"
        f"{PLATFORM_META.get(binding.provider, {}).get('name', 'IM')}）与你对话。\n\n"
        "你可以帮助用户：\n"
        "1. **查询信息**：项目进度、任务列表、风险状况、里程碑、资源日历等\n"
        "2. **创建内容**：新建任务、项目、风险登记、变更请求等\n"
        "3. **更新数据**：修改任务状态、更新进度、调整优先级等\n"
        "4. **分析决策**：EVM分析、风险预测、资源优化建议等\n"
        "5. **审批操作**：通过/拒绝待审批项\n\n"
        "重要规则：\n"
        "- 操作前必须确认用户意图，不确定时主动询问\n"
        "- 涉及修改/删除操作时，简要告知用户将执行什么\n"
        "- 用简洁的中文回复（IM场景不宜过长）\n"
        "- 数据用表格或列表呈现更清晰\n"
        f"- 用户默认项目ID: {project_id or '未设置'}\n"
    )

    try:
        # 优先直接对接服务器本地 OpenClaw Gateway（飞书→OpenClaw 核心链路）
        openclaw_reply = await _call_openclaw(message, session_key=binding.im_user_id)
        if openclaw_reply:
            reply = openclaw_reply
            logger.info("AI 回复来自 OpenClaw")
        else:
            # Fallback: 使用内置 ai_service (minimax)
            from app.services.ai_service import ai_service
            response = await ai_service.chat(
                message=message,
                project_id=project_id,
                context={
                    "_source": "im_gateway",
                    "_provider": binding.provider,
                    "_session_id": session_id,
                    "_system_override": im_system_prompt,
                },
            )
            reply = response.get("message", "抱歉，我暂时无法处理您的请求。")
            logger.info("AI 回复来自 ai_service (minimax fallback)")
        
        # 尝试从回复中提取结构化操作指令
        parsed_intent = _extract_intent_from_response(reply, message)
        
        return {
            "reply_text": reply,
            "reply_type": "text",
            "actions_taken": parsed_intent.get("actions", []),
            "parsed_intent": parsed_intent,
            "action_category": parsed_intent.get("category", "query"),
            "result_status": "success",
        }
    except Exception as e:
        return {
            "reply_text": f"处理出错: {str(e)}",
            "actions_taken": [],
            "result_status": "error",
            "error_message": str(e),
        }


def _extract_intent_from_response(ai_reply: str, user_message: str) -> Dict[str, Any]:
    """
    从AI回复中提取结构化意图。
    这是一个轻量级解析器——未来可替换为 function calling 或 tool use。
    """
    msg_lower = user_message.lower().strip()
    intent = {"category": "query", "actions": [], "confidence": 0.5}
    
    # 操作关键词检测
    create_keywords = ["新建", "创建", "添加", "新增", "开一个", "建个"]
    update_keywords = ["修改", "更新", "改", "编辑", "设置", "调整为"]
    delete_keywords = ["删除", "移除", "取消", "关闭"]
    approve_keywords = ["批准", "通过", "同意", "ok", "好的", "确认"]
    reject_keywords = ["拒绝", "驳回", "不行", "不同意"]

    if any(kw in msg_lower for kw in create_keywords):
        intent["category"] = "create"
        intent["actions"].append({"type": "create", "raw": user_message})
        intent["confidence"] = 0.8
    elif any(kw in msg_lower for kw in update_keywords):
        intent["category"] = "update"
        intent["actions"].append({"type": "update", "raw": user_message})
        intent["confidence"] = 0.8
    elif any(kw in msg_lower for kw in delete_keywords):
        intent["category"] = "delete"
        intent["actions"].append({"type": "delete", "raw": user_message})
        intent["confidence"] = 0.8
    elif any(kw in msg_lower for kw in approve_keywords):
        intent["category"] = "update"
        intent["actions"].append({"type": "approve", "raw": user_message})
        intent["confidence"] = 0.7
    elif any(kw in msg_lower for kw in reject_keywords):
        intent["category"] = "update"
        intent["actions"].append({"type": "reject", "raw": user_message})
        intent["confidence"] = 0.7
    else:
        intent["category"] = "query"
        intent["confidence"] = 0.6

    return intent


async def _detect_conflicts(
    db: AsyncSession,
    user_id: str,
    actions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    冲突检测引擎：
    检测并发操作冲突、资源冲突、时间冲突等。
    """
    if not actions:
        return []

    conflicts = []
    
    for action in actions:
        action_type = action.get("type")
        
        # 并发编辑冲突检测：同一任务短时间内被多人修改
        if action_type in ("update", "delete"):
            entity_id = action.get("entity_id")
            if entity_id:
                # 查找最近30秒内其他用户对同一实体的操作
                recent_ops = await db.execute(
                    select(IMAuditLog).where(
                        IMAuditLog.executed_action.astext.like(f"%{entity_id}%"),
                        IMAuditLog.user_id != user_id,
                        IMAuditLog.created_at >= datetime.now().replace(
                            second=datetime.now().second - 30
                        ),
                    )
                )
                recent = recent_ops.scalars().all()
                if recent:
                    conflicts.append({
                        "type": "concurrent_edit",
                        "entity_id": entity_id,
                        "description": (
                            f"该资源正在被其他用户同时操作（{len(recent)}个并发操作），"
                            f"可能产生冲突。建议稍后再试或协调操作顺序。"
                        ),
                        "severity": "warning",
                        "competing_users": list(set([r.user_id for r in recent])),
                    })

        # 资源分配冲突：同一人员同一时间段被分配多个任务
        if action_type == "create":
            raw = action.get("raw", "")
            if any(kw in raw.lower() for kw in ["分配", "指派", "assign"]):
                conflicts.append({
                    "type": "resource_allocation",
                    "description": "检测到资源分配操作，请确认该人员在该时段是否有空闲。",
                    "severity": "info",
                })

    return conflicts


# ============================================================
# 飞书 API 工具（发送回复消息）
# ============================================================
FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


def _fetch_tenant_token_sync(app_id: str, app_secret: str) -> Optional[str]:
    """同步获取飞书 tenant_access_token（放到线程池执行，避免阻塞事件循环）"""
    try:
        url = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
        data = json.dumps({
            "app_id": app_id,
            "app_secret": app_secret,
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        if result.get("code") == 0:
            return result["tenant_access_token"]
        logger.error(f"飞书 token 返回错误: {result}")
    except Exception as e:
        logger.error(f"获取飞书 token 失败: {e}")
    return None


async def _get_feishu_token(db: AsyncSession) -> Optional[str]:
    """异步获取已配置飞书的 tenant_access_token（DB 读取异步，HTTP 调用走线程池）"""
    result = await db.execute(
        select(IMProviderConfig).where(IMProviderConfig.provider == "feishu")
    )
    config = result.scalar_one_or_none()
    if not config or not config.app_id or not config.app_secret:
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _fetch_tenant_token_sync, config.app_id, config.app_secret
    )


def _send_feishu_reply_sync(token: str, receive_id: str, text: str, receive_id_type: str = "open_id") -> bool:
    """同步发送飞书消息（在线程池中执行）"""
    try:
        url = f"{FEISHU_API_BASE}/im/v1/messages?receive_id_type={receive_id_type}"
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        if result.get("code") == 0:
            msg_id = (result.get("data") or {}).get("message_id") or (result.get("data") or {}).get("msgid")
            logger.info(f"飞书回复已发送: msg_id={msg_id}")
            return True
        logger.error(f"飞书回复发送失败: {result}")
        return False
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode(errors="replace")
        except Exception:
            body = ""
        logger.error(f"发送飞书回复失败 HTTP {e.code}: {body[:300]}")
        return False
    except Exception as e:
        logger.error(f"发送飞书回复失败: {e}")
        return False


async def _send_feishu_reply(receive_id: str, text: str, receive_id_type: str = "open_id") -> bool:
    """异步发送飞书回复（独立会话取 token，脱离请求生命周期；超长自动分片）"""
    from app.db.session import async_session_maker
    async with async_session_maker() as db:
        token = await _get_feishu_token(db)
    if not token:
        logger.warning("无法获取飞书 token，跳过回复")
        return False
    loop = asyncio.get_event_loop()
    # 飞书 text 消息有长度限制，超长分多条发送，避免 400 input length too long
    MAX = 2000
    chunks = [text[i:i + MAX] for i in range(0, len(text), MAX)] or [text]
    ok = True
    for i, chunk in enumerate(chunks):
        sent = await loop.run_in_executor(None, _send_feishu_reply_sync, token, receive_id, chunk, receive_id_type)
        ok = ok and sent
    return ok


# ============================================================
# OpenClaw 桥接（直接对接服务器本地 OpenClaw Gateway）
# ============================================================
# OpenClaw 以 Gateway 模式运行（WebSocket），其 CLI `agent` 子命令可发起
# 一次完整的 agent 回合并输出 JSON 结果。这是「飞书 → OpenClaw」对接的核心。
OPENCLAW_NODE = "/home/ubuntu/.nvm/versions/node/v22.22.3/bin/node"
OPENCLAW_BIN = "/home/ubuntu/.local/share/pnpm/global/5/.pnpm/openclaw@2026.6.11/node_modules/openclaw/openclaw.mjs"
OPENCLAW_ENV = {
    # 复用 ubuntu 用户的 OpenClaw 配置（Gateway token / basePath 已就绪）
    "OPENCLAW_CONFIG_PATH": "/home/ubuntu/.openclaw/openclaw.json",
    "OPENCLAW_STATE_DIR": "/home/ubuntu/.openclaw",
    "HOME": "/home/ubuntu",
    "PATH": "/home/ubuntu/.nvm/versions/node/v22.22.3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
}

# 并发信号量：同一时刻最多 1 个 openclaw agent 调用。
# 原因：每次调用都会派生 node + 无头 chromium，3.7GB 小内存 VPS 上
# 并发多个会让内存瞬间爆掉触发 OOM（已发生过）。串行化避免内存尖峰。
OPENCLAW_SEM = asyncio.Semaphore(1)
OPENCLAW_HARD_TIMEOUT = 150  # 秒


def _strip_think(text: str) -> str:
    """移除模型思考链标签 <think>...</think>，避免推理过程泄漏到飞书消息。"""
    if not text:
        return text
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


async def _call_openclaw(message: str, session_key: str = "main") -> Optional[str]:
    """
    调用服务器本地 OpenClaw Gateway 的 agent 命令获取 AI 回复。

    - 直接对接 OpenClaw（飞书消息经此获得 OpenClaw 的回答）
    - 每个飞书用户使用独立 session-key，保留对话上下文
    - 串行化（信号量）避免并发派生多个 chromium 撑爆内存
    - 超时强杀整棵进程树（含 chromium 子进程），杜绝僵尸/泄漏
    - 失败返回 None，由上层 fallback 到 ai_service(minimax)
    """
    async with OPENCLAW_SEM:
        try:
            full_message = (
                "你正在通过飞书为「PMI中国 AI-PM」用户提供智能项目管理助手服务，"
                "请用简洁、专业、口语化的中文回复，避免长篇大论。\n\n"
                f"用户消息：{message}"
            )
            cmd = [
                OPENCLAW_NODE, OPENCLAW_BIN, "agent",
                "--message", full_message,
                "--json",
                "--session-key", f"feishu:{session_key}",
                "--timeout", "120",
            ]
            env = {**os.environ, **OPENCLAW_ENV}
            # start_new_session=True → 建立独立进程组，便于整体强杀
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                start_new_session=True,
            )

            def _kill_tree():
                try:
                    # 杀掉整个进程组（含 openclaw 派生的 chromium）
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=OPENCLAW_HARD_TIMEOUT
                )
            except asyncio.TimeoutError:
                _kill_tree()
                try:
                    await proc.wait()
                except Exception:
                    pass
                logger.error(f"OpenClaw agent 调用超时（{OPENCLAW_HARD_TIMEOUT}s），已强杀进程树")
                return None
            except Exception:
                _kill_tree()
                raise
            if proc.returncode != 0:
                logger.error(
                    f"OpenClaw agent 失败 rc={proc.returncode}: "
                    f"{stderr.decode(errors='replace')[:500]}"
                )
                return None
            data = json.loads(stdout.decode(errors="replace"))
            if data.get("status") == "ok":
                payloads = data.get("result", {}).get("payloads", [])
                text = "".join(p.get("text", "") for p in payloads if p.get("text"))
                text = _strip_think(text)
                return text.strip() or None
            logger.warning(f"OpenClaw agent 返回非 ok 状态: {data.get('status')}")
            return None
        except Exception as e:
            logger.exception("OpenClaw 调用异常")
            return None

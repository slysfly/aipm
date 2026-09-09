"""
PMI中国AI项目管理社区 - Zapier/Make集成API
遵循Zapier REST Hook规范，支持Polling和REST Hook两种触发模式

[PMBOK KA: 跨领域 (Cross-area) — Zapier集成、自动化工作流]
对应PMI第6版标准：外部自动化
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header, Body
from pydantic import BaseModel, Field

from app.config import settings
from app.core.security import get_current_user
from app.models import User
from app.services.zapier_integration import (
    zapier_service,
    zapier_webhook_store,
    notify_zapier_event,
    ZapierEventType,
    ZAPIER_TRIGGERS,
    SAMPLE_DATA_TEMPLATES,
)

router = APIRouter(prefix="/zapier", tags=["Zapier集成"])

logger = logging.getLogger("app.api.v1.zapier")

# 若未配置 Webhook 签名密钥，则写操作在请求时将一律拒绝（见 receive_webhook），
# 避免未签名请求伪造数据写入系统。
if not settings.ZAPIER_WEBHOOK_SECRET:
    logger.warning(
        "未配置 ZAPIER_WEBHOOK_SECRET：Zapier Webhook 写操作"
        "（create_task/create_project/update_task）将在请求时返回 403 拒绝，"
        "以避免未签名请求伪造数据。"
    )


# ============ 请求/响应模型 ============

class ZapierAuthRequest(BaseModel):
    api_key: str = Field(..., description="API密钥")


class ZapierAuthResponse(BaseModel):
    success: bool
    message: str
    user: Optional[Dict[str, Any]] = None


class ZapierSubscribeRequest(BaseModel):
    trigger_id: str = Field(..., description="触发器ID")
    hook_url: str = Field(..., description="Zapier提供的hook URL")
    secret: Optional[str] = Field(None, description="可选的webhook密钥")


class ZapierSubscribeResponse(BaseModel):
    subscription_id: str
    trigger_id: str
    hook_url: str
    secret: str
    created_at: str


class ZapierWebhookActionRequest(BaseModel):
    action: str = Field(..., description="动作类型: create_task, update_task, create_project")
    data: Dict[str, Any] = Field(default_factory=dict, description="动作数据")


class ZapierWebhookActionResponse(BaseModel):
    success: bool
    action: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ZapierTriggerItem(BaseModel):
    id: str
    name: str
    description: str
    event_type: str


class ZapierTriggerListResponse(BaseModel):
    triggers: List[ZapierTriggerItem]


class ZapierTestConnectionResponse(BaseModel):
    success: bool
    message: str
    timestamp: str
    version: str


# ============ API端点 ============

@router.get("/triggers", response_model=ZapierTriggerListResponse)
async def get_triggers(
    current_user: User = Depends(get_current_user)
):
    """获取可用的触发器列表（Zapier拉取）
    
    Zapier使用此端点获取用户可以订阅的所有触发器。
    支持Polling模式：Zapier会定期轮询此端点检查新数据。
    """
    triggers = zapier_service.get_available_triggers()
    return ZapierTriggerListResponse(triggers=[
        ZapierTriggerItem(**t) for t in triggers
    ])


@router.get("/sample-data")
async def get_sample_data(
    trigger_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """提供示例数据（Zapier测试用）
    
    Zapier在设置Zap时使用此端点获取示例数据，
    帮助用户映射字段。
    """
    return {
        "success": True,
        "data": zapier_service.get_sample_data(trigger_id)
    }


@router.post("/auth", response_model=ZapierAuthResponse)
async def zapier_auth(
    request: ZapierAuthRequest,
    current_user: User = Depends(get_current_user)
):
    """Zapier 认证验证

    Zapier 在连接应用时调用此端点验证 API 密钥。
    此处按系统对外 API Key 机制校验用户提交的 api_key（SHA-256 哈希比对），
    无效或已禁用的 Key 一律拒绝认证。
    """
    from app.models.api_key import ApiKey, hash_api_key
    from app.db.session import async_session_maker

    async with async_session_maker() as db:
        result = await db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == hash_api_key(request.api_key),
                ApiKey.is_active == True,  # noqa: E712
            )
        )
        api_key_row = result.scalar_one_or_none()
        if not api_key_row:
            logger.warning("Zapier 认证失败：提供的 API Key 无效或已禁用")
            return ZapierAuthResponse(success=False, message="API Key 无效或已禁用")
        api_key_row.last_used_at = datetime.now()
        await db.commit()

    return ZapierAuthResponse(
        success=True,
        message="认证成功",
        user={
            "id": current_user.id,
            "email": getattr(current_user, 'email', ''),
            "username": getattr(current_user, 'username', ''),
            "full_name": getattr(current_user, 'full_name', ''),
        }
    )


@router.post("/subscribe")
async def subscribe_webhook(
    request: ZapierSubscribeRequest,
    current_user: User = Depends(get_current_user)
):
    """订阅Zapier webhook（REST Hook模式）
    
    当用户在Zapier中开启Zap时，Zapier会调用此端点
    注册一个hook URL，后续事件发生时我们会推送至此URL。
    """
    # 验证触发器ID是否有效
    valid_trigger_ids = [t["id"] for t in ZAPIER_TRIGGERS]
    if request.trigger_id not in valid_trigger_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的触发器ID: {request.trigger_id}"
        )

    sub_id = await zapier_webhook_store.subscribe(
        trigger_id=request.trigger_id,
        hook_url=request.hook_url,
        user_id=current_user.id,
        secret=request.secret,
    )

    subscription = await zapier_webhook_store.get_subscription(sub_id)

    return {
        "success": True,
        "data": {
            "subscription_id": sub_id,
            "trigger_id": request.trigger_id,
            "hook_url": request.hook_url,
            "secret": subscription["secret"],
            "created_at": subscription["created_at"],
        }
    }


@router.post("/unsubscribe")
async def unsubscribe_webhook(
    subscription_id: str,
    current_user: User = Depends(get_current_user)
):
    """取消订阅Zapier webhook
    
    当用户在Zapier中关闭Zap时，Zapier会调用此端点
    取消之前的hook订阅。
    """
    success = await zapier_webhook_store.unsubscribe(subscription_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="订阅不存在"
        )

    return {
        "success": True,
        "data": {"subscription_id": subscription_id, "status": "unsubscribed"}
    }


@router.post("/webhook", response_model=ZapierWebhookActionResponse)
async def receive_webhook(
    request: Request,
    action_request: ZapierWebhookActionRequest,
    x_zapier_signature: Optional[str] = Header(None),
    current_user: User = Depends(get_current_user)
):
    """Zapier webhook接收端点
    
    接收来自Zapier的动作请求，支持：
    - create_task: 创建任务
    - update_task: 更新任务
    - create_project: 创建项目
    
    写操作必须携带有效的 X-Zapier-Signature 签名；服务端未配置签名密钥时，
    写操作端点直接拒绝启用（返回 403），而不是静默放行。
    """
    action = action_request.action
    data = action_request.data

    # 写操作强制要求签名校验
    WRITE_ACTIONS = {"create_task", "update_task", "create_project"}
    if action in WRITE_ACTIONS:
        if not settings.ZAPIER_WEBHOOK_SECRET:
            logger.warning(
                "Zapier Webhook 写操作被拒绝：服务端未配置 ZAPIER_WEBHOOK_SECRET，无法校验签名。"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="服务端未配置 Webhook 签名密钥，写操作已禁用",
            )
        if not x_zapier_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少 X-Zapier-Signature 签名头",
            )
        body = await request.body()
        is_valid = zapier_service.validate_webhook_signature(
            x_zapier_signature, body, settings.ZAPIER_WEBHOOK_SECRET
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="签名验证失败",
            )

    # 非写操作无需签名（保持原有行为）

    try:
        if action == "create_task":
            result = await _handle_create_task(data, current_user)
        elif action == "update_task":
            result = await _handle_update_task(data, current_user)
        elif action == "create_project":
            result = await _handle_create_project(data, current_user)
        elif action == "ping":
            result = {"message": "pong", "timestamp": datetime.now().isoformat()}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的动作: {action}"
            )

        return ZapierWebhookActionResponse(
            success=True,
            action=action,
            result=result
        )

    except HTTPException:
        raise
    except Exception as e:
        return ZapierWebhookActionResponse(
            success=False,
            action=action,
            error=str(e)
        )


@router.get("/ping")
async def ping(
    current_user: User = Depends(get_current_user)
):
    return ZapierTestConnectionResponse(
        success=True,
        message="连接成功",
        timestamp=datetime.now().isoformat(),
        version="1.0.0"
    )


@router.post("/test-connection")
async def test_connection(
    current_user: User = Depends(get_current_user)
):
    return {
        "success": True,
        "data": {
            "connected": True,
            "user_id": current_user.id,
            "username": getattr(current_user, 'username', ''),
            "timestamp": datetime.now().isoformat(),
        }
    }


@router.get("/polling/{trigger_id}")
async def polling_endpoint(
    trigger_id: str,
    since: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Zapier Polling端点
    
    对于不支持REST Hook的触发器，Zapier使用轮询模式。
    此端点返回自上次检查以来的新数据。
    
    since参数：ISO格式时间戳，表示上次检查时间
    """
    # 验证触发器ID
    valid_trigger_ids = [t["id"] for t in ZAPIER_TRIGGERS]
    if trigger_id not in valid_trigger_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的触发器ID: {trigger_id}"
        )

    # 从数据库真实查询自 since 时间以来的新数据（Zapier polling 期望数组格式）
    from app.db.session import async_session_maker
    from app.models import Task, Project, Comment
    from sqlalchemy import select

    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except Exception:
            since_dt = None

    items = []
    async with async_session_maker() as db:
        if trigger_id in ("task.created", "task.updated", "task.completed"):
            q = select(Task).where(
                Task.is_deleted == False,
            )
            # 超管可访问所有项目；普通用户仅可见自己拥有或参与的项目
            if not current_user.is_superuser:
                from app.models import ProjectMember
                accessible_project_ids_q = (
                    select(Project.id).where(
                        (Project.owner_id == current_user.id)
                        | (Project.id.in_(
                            select(ProjectMember.project_id).where(
                                ProjectMember.user_id == current_user.id
                            )
                        ))
                    )
                )
                q = q.where(Task.project_id.in_(accessible_project_ids_q))
            if since_dt:
                q = q.where(Task.created_at >= since_dt)
            q = q.order_by(Task.created_at.desc()).limit(20)
            rows = (await db.execute(q)).scalars().all()
            items = [
                {
                    "id": t.id,
                    "name": t.name,
                    "status": t.status,
                    "project_id": t.project_id,
                    "progress": float(t.progress) if t.progress else 0,
                }
                for t in rows
            ]
        elif trigger_id == "project.created":
            # 仅返回当前用户拥有或参与的项目
            from app.models import ProjectMember
            member_project_ids = (
                select(ProjectMember.project_id).where(
                    ProjectMember.user_id == current_user.id
                )
            )
            q = select(Project).where(
                Project.is_deleted == False,
                (Project.owner_id == current_user.id)
                | (Project.id.in_(member_project_ids))
                | (current_user.is_superuser == True),
            )
            if since_dt:
                q = q.where(Project.created_at >= since_dt)
            q = q.order_by(Project.created_at.desc()).limit(20)
            rows = (await db.execute(q)).scalars().all()
            items = [{"id": p.id, "name": p.name, "status": p.status} for p in rows]
        elif trigger_id == "comment.added":
            # 评论归属校验：通过 Task → Project 链路验证当前用户可访问
            q = select(Comment).join(Task, Comment.task_id == Task.id).join(Project, Task.project_id == Project.id).where(Comment.is_deleted == False)
            if not current_user.is_superuser:
                from app.models import ProjectMember
                q = q.where((Project.owner_id == current_user.id) | (Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == current_user.id))))
            if since_dt:
                q = q.where(Comment.created_at >= since_dt)
            q = q.order_by(Comment.created_at.desc()).limit(20)
            rows = (await db.execute(q)).scalars().all()
            items = [{"id": c.id, "content": c.content, "task_id": c.task_id} for c in rows]

    return items


# ============ 内部处理函数 ============

async def _handle_create_task(data: Dict[str, Any], user: User) -> Dict[str, Any]:
    from app.db.session import async_session_maker

    async with async_session_maker() as db:
        from sqlalchemy import select
        from app.models import Task, Project

        # 验证项目存在
        project_id = data.get("project_id")
        if project_id:
            result = await db.execute(
                select(Project).where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="项目不存在"
                )

        task = Task(
            project_id=project_id,
            name=data.get("name", "未命名任务"),
            description=data.get("description", ""),
            status=data.get("status", "todo"),
            priority=data.get("priority", 3),
            assignee_id=data.get("assignee_id"),
            estimated_hours=data.get("estimated_hours", 0),
            labels=data.get("labels", []),
            category=data.get("category", ""),
        )

        db.add(task)
        await db.commit()
        await db.refresh(task)

        return {
            "id": task.id,
            "name": task.name,
            "status": task.status,
            "project_id": task.project_id,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }


async def _handle_update_task(data: Dict[str, Any], user: User) -> Dict[str, Any]:
    from app.db.session import async_session_maker

    async with async_session_maker() as db:
        from sqlalchemy import select
        from app.models import Task

        task_id = data.get("task_id")
        if not task_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="缺少task_id"
            )

        result = await db.execute(
            select(Task).where(Task.id == task_id, Task.is_deleted == False)
        )
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="任务不存在"
            )

        # 更新字段
        updateable_fields = [
            "name", "description", "status", "priority",
            "assignee_id", "estimated_hours", "labels", "category"
        ]

        for field in updateable_fields:
            if field in data:
                setattr(task, field, data[field])

        task.updated_at = datetime.now()
        await db.commit()
        await db.refresh(task)

        return {
            "id": task.id,
            "name": task.name,
            "status": task.status,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }


async def _handle_create_project(data: Dict[str, Any], user: User) -> Dict[str, Any]:
    from app.db.session import async_session_maker

    async with async_session_maker() as db:
        from app.models import Project

        project = Project(
            name=data.get("name", "未命名项目"),
            description=data.get("description", ""),
            status=data.get("status", "planning"),
            priority=data.get("priority", 3),
            color=data.get("color", "#1890ff"),
            owner_id=user.id,
            industry_type=data.get("industry_type", "it_software"),
            project_type=data.get("project_type", "agile"),
            budget=data.get("budget", 0),
        )

        db.add(project)
        await db.commit()
        await db.refresh(project)

        return {
            "id": project.id,
            "name": project.name,
            "status": project.status,
            "owner_id": project.owner_id,
            "created_at": project.created_at.isoformat() if project.created_at else None,
        }

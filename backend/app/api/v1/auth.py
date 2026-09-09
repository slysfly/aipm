"""
[PMBOK KA: 相关方管理 (Stakeholder) — 用户认证、访问控制、干系人识别]
对应PMI第6版标准：干系人识别、访问控制
"""

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta

from app.db.session import get_db
from app.models import User
from app.schemas import UserLogin, Token, UserCreate, UserResponse, SuccessResponse
from app.core.security import (
    verify_password, get_password_hash, 
    create_access_token, create_refresh_token,
    get_current_user
)
from app.core.exceptions import AuthenticationException
from app.config import settings

router = APIRouter()

# 登录速率限制（内存，每IP）
_login_attempts: dict = defaultdict(lambda: {"count": 0, "first_attempt": 0.0})
_LOGIN_RATE_LIMIT = 5        # 最多失败次数
_LOGIN_RATE_WINDOW = 60      # 窗口（秒）
_LOGIN_BAN_DURATION = 900    # 封禁时长（秒）


def _check_login_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    record = _login_attempts[client_ip]
    now = time.time()

    # 封禁期内直接拒绝
    if record["count"] >= _LOGIN_RATE_LIMIT:
        elapsed = now - record["first_attempt"]
        if elapsed < _LOGIN_BAN_DURATION:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"登录尝试过于频繁，请在 {int(_LOGIN_BAN_DURATION - elapsed)} 秒后重试"
            )
        # 封禁期满重置
        record["count"] = 0
        record["first_attempt"] = 0.0

    # 窗口过期重置
    if now - record["first_attempt"] > _LOGIN_RATE_WINDOW:
        record["count"] = 0
        record["first_attempt"] = now


def _record_login_failure(request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    record = _login_attempts[client_ip]
    now = time.time()
    if record["count"] == 0:
        record["first_attempt"] = now
    record["count"] += 1


def _clear_login_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    _login_attempts.pop(client_ip, None)


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    # 检查邮箱是否已存在
    result = await db.execute(
        select(User).where(User.email == user_in.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册"
        )
    
    # 检查用户名是否已存在
    result = await db.execute(
        select(User).where(User.username == user_in.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已被使用"
        )
    
    # 创建用户
    user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        phone=user_in.phone,
        department=user_in.department,
        position=user_in.position,
        is_superuser=False,  # 服务端强制：注册接口不允许自提权
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return user


@router.post("/login")
async def login(
    login_in: UserLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    
    """返回 JSON 令牌同时设置 httpOnly Cookie，双重兼容：
    - 新客户端优先使用 Cookie（防 XSS 窃取）
    - 旧客户端可继续使用 Authorization header
    """
    # 速率限制检查
    _check_login_rate_limit(request)

    # 查找用户（支持邮箱或用户名登录）
    result = await db.execute(
        select(User).where(
            (User.email == login_in.username) | (User.username == login_in.username)
        )
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(login_in.password, user.hashed_password):
        _record_login_failure(request)
        raise AuthenticationException(message="用户名或密码错误")
    
    if not user.is_active:
        _record_login_failure(request)
        raise AuthenticationException(message="用户已被禁用")
    
    # 登录成功清除失败记录
    _clear_login_rate_limit(request)
    
    # 生成令牌
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(data={"sub": user.id})
    
    # 设置 httpOnly Cookie（防 XSS 窃取，生产环境建议加上 Secure 和 SameSite=Lax）
    cookie_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=cookie_max_age,
        httponly=True,
        samesite="lax",
        # secure=True,  # 生产环境启用 HTTPS 时取消注释
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        samesite="lax",
        # secure=True,
    )
    
    return {
        "code": 200,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": cookie_max_age,
        },
        "message": "登录成功",
    }


class MeResponse(BaseModel):
    user: UserResponse
    access_token: str
    refresh_token: str


@router.get("/me", response_model=MeResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    # 浏览器整页刷新后，前端内存态令牌为空；此处随 Cookie 鉴权成功回签 access/refresh token，
    # 使前端重建内存态令牌与实时通道，避免刷新后被误判为未登录。仅回签、不延长用户主动会话有效期。
    access_token = create_access_token(
        data={"sub": current_user.id},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token = create_refresh_token(data={"sub": current_user.id})
    return MeResponse(user=current_user, access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh")
async def refresh_token(
    refresh_req: dict,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import decode_token
    
    refresh_token_str = refresh_req.get("refresh_token") if refresh_req else None
    if not refresh_token_str:
        raise AuthenticationException(message="刷新令牌不能为空")

    try:
        payload = decode_token(refresh_token_str)

        if payload.get("type") != "refresh":
            raise AuthenticationException(message="无效的刷新令牌")
        
        user_id = payload.get("sub")
        
        # 查找用户
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise AuthenticationException(message="用户不存在或已禁用")
        
        # 生成新令牌
        new_access_token = create_access_token(
            data={"sub": user.id},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        new_refresh_token = create_refresh_token(data={"sub": user.id})
        
        cookie_max_age = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        response.set_cookie(
            key="access_token", value=new_access_token,
            max_age=cookie_max_age, httponly=True, samesite="lax",
        )
        response.set_cookie(
            key="refresh_token", value=new_refresh_token,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            httponly=True, samesite="lax",
        )
        
        return {
            "code": 200,
            "data": {
                "access_token": new_access_token,
                "refresh_token": new_refresh_token,
                "expires_in": cookie_max_age,
            },
            "message": "刷新成功",
        }
    except Exception:
        raise AuthenticationException(message="无效的刷新令牌")


@router.post("/logout")
async def logout(response: Response):
    """退出登录：清除服务端下发的 httpOnly Cookie。

    由于 Cookie 标记为 httponly，前端 JS（含被注入的恶意脚本）无法读取或清除，
    只能由本次请求经后端删除，从根本上杜绝 XSS 窃取持久令牌。
    该端点不强制鉴权，确保任何状态下都能安全清 Cookie。
    """
    response.delete_cookie("access_token", samesite="lax")
    response.delete_cookie("refresh_token", samesite="lax")
    return {"code": 200, "message": "已退出登录", "data": None}

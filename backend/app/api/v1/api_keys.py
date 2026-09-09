"""
[PMBOK KA: 相关方管理 (Stakeholder) — API密钥管理、访问令牌]
对应PMI第6版标准：API密钥管理、访问控制
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.api_key import ApiKey, generate_api_key, hash_api_key
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyResponse
from app.core.security import require_superuser
from app.models import User
from app.services.external_api_config import load_config, save_config

router = APIRouter()


class ExternalApiConfigUpdate(BaseModel):
    enabled: bool
    public_base_url: Optional[str] = None
    note: Optional[str] = None


@router.get("/external-api-config")
async def get_external_api_config(_: User = Depends(require_superuser)):
    """获取对外 API（外部对接）启用状态与配置。"""
    return load_config()


@router.put("/external-api-config")
async def update_external_api_config(
    payload: ExternalApiConfigUpdate,
    current_user: User = Depends(require_superuser),
):
    """设置对外 API（外部对接）是否开放端口，并可指定对外访问地址。"""
    return save_config(payload.enabled, payload.public_base_url, payload.note, current_user.username)


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_superuser),
):
    raw = generate_api_key()
    key = ApiKey(
        name=payload.name,
        key_hash=hash_api_key(raw),
        key_prefix=raw[:12],
        scopes=payload.scopes,
        created_by=current_user.id,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    key._plain_key = raw  # type: ignore[attr-defined]
    return ApiKeyCreatedResponse(**key.to_dict(include_key=True))


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_superuser),
):
    result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return [ApiKeyResponse(**k.to_dict()) for k in result.scalars().all()]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_superuser),
):
    key = (await db.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    await db.delete(key)
    await db.commit()
    return None

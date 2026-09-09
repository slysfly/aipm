"""
PMI中国AI项目管理社区 — 可自定义项目类型 API

提供项目类型的增删改查。项目类型由用户在同一套全局列表中自定义，
替代原先写死的 ProjectType 枚举。Project.project_type 存放本表的 code。

权限：列表需登录；创建/更新/删除需超级管理员（集中管理）。
"""

import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.db.session import get_db
from app.models import ProjectType, Project, User
from app.core.security import get_current_user
from app.core.responses import success

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 请求/响应模型 ====================

class ProjectTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: Optional[str] = Field(None, max_length=50, description="稳定标识；留空则按名称自动生成，创建后不可更改")
    color: str = Field(default="#1890ff", max_length=7)
    description: Optional[str] = None
    sort_order: int = 0


class ProjectTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, max_length=7)
    description: Optional[str] = None
    sort_order: Optional[int] = None


class ProjectTypeResponse(BaseModel):
    id: str
    name: str
    code: str
    color: str
    description: Optional[str]
    is_system: bool
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ==================== 工具 ====================

def _slugify(text: str) -> str:
    """将名称转换为 code：小写、非字母数字转下划线、去重、去首尾"""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    # 含中文时回退为短 uuid，避免 code 含中文导致可读性/兼容问题
    if any("\u4e00" <= ch <= "\u9fa5" for ch in s):
        s = "pt_" + uuid.uuid4().hex[:8]
    return s[:50]


async def _ensure_unique_code(db: AsyncSession, code: str, exclude_id: Optional[str] = None) -> None:
    stmt = select(func.count(ProjectType.id)).where(ProjectType.code == code)
    if exclude_id:
        stmt = stmt.where(ProjectType.id != exclude_id)
    cnt = (await db.execute(stmt)).scalar() or 0
    if cnt > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"类型标识(code)已存在：{code}")


# ==================== 端点 ====================

@router.get("", response_model=List[ProjectTypeResponse])
async def list_project_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出全部项目类型（按排序、名称）"""
    stmt = select(ProjectType).order_by(ProjectType.sort_order, ProjectType.name)
    res = (await db.execute(stmt)).scalars().all()
    return [ProjectTypeResponse.model_validate(t) for t in res]


@router.post("", response_model=ProjectTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_project_type(
    payload: ProjectTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅超级管理员可管理项目类型")
    code = payload.code or _slugify(payload.name)
    code = code.strip("_") or ("pt_" + uuid.uuid4().hex[:8])
    await _ensure_unique_code(db, code)
    pt = ProjectType(
        name=payload.name.strip(),
        code=code,
        color=payload.color,
        description=payload.description,
        sort_order=payload.sort_order,
        is_system=False,
    )
    db.add(pt)
    await db.commit()
    await db.refresh(pt)
    return ProjectTypeResponse.model_validate(pt)


@router.put("/{type_id}", response_model=ProjectTypeResponse)
async def update_project_type(
    type_id: str,
    payload: ProjectTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅超级管理员可管理项目类型")
    pt = (await db.execute(select(ProjectType).where(ProjectType.id == type_id))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目类型不存在")
    if payload.name is not None:
        pt.name = payload.name.strip()
    if payload.color is not None:
        pt.color = payload.color
    if payload.description is not None:
        pt.description = payload.description
    if payload.sort_order is not None:
        pt.sort_order = payload.sort_order
    await db.commit()
    await db.refresh(pt)
    return ProjectTypeResponse.model_validate(pt)


@router.delete("/{type_id}", status_code=status.HTTP_200_OK)
async def delete_project_type(
    type_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅超级管理员可管理项目类型")
    pt = (await db.execute(select(ProjectType).where(ProjectType.id == type_id))).scalar_one_or_none()
    if not pt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目类型不存在")
    # 被项目引用则禁止删除，避免悬空引用
    used = (await db.execute(
        select(func.count(Project.id)).where(Project.project_type == pt.code)
    )).scalar() or 0
    if used > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"该类型已被 {used} 个项目使用，无法删除。请先将这些项目的类型改为其他类型。",
        )
    await db.delete(pt)
    await db.commit()
    return success(message="已删除项目类型")

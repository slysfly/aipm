"""
PMI中国AI项目管理社区 - 应用市场/插件生态 API端点

[PMBOK KA: 采购管理 (Procurement) — 应用市场、供应商管理]
对应PMI第6版标准：供应商管理、采购管理
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field, ConfigDict

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.app_market import AppPlugin, AppInstallation
from app.schemas.app_market import (
    AppPluginCreate, AppPluginUpdate, AppPluginResponse, AppPluginListResponse,
    AppInstallationUpdate, AppInstallationResponse, AppInstallationListResponse,
    PluginInstallRequest, PluginRateRequest,
)
# 导入 Plugin SDK 注册表与查询函数（import 即触发官方插件注册副作用）
# 注意：本模块已定义同名 async def list_plugins（GET /plugins 路由），故此处用别名避免遮蔽
from app.services.integrations.plugin_sdk import PLUGIN_REGISTRY, get_plugin, list_plugins as sdk_list_plugins  # noqa: F401
import app.services.integrations  # 确保官方插件完成注册

router = APIRouter()


class PluginExecuteRequest(BaseModel):
    """插件执行请求：指定项目与触发上下文"""
    model_config = ConfigDict(from_attributes=True)

    project_id: str = Field(..., description="安装插件的项目 ID")
    context: Dict[str, Any] = Field(default_factory=dict, description="触发上下文，如 event/user_id 等")


@router.get("/plugins", response_model=AppPluginListResponse)
async def list_plugins(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None, pattern="^(integration|automation|report|ai|utility)$"),
    status: str = Query("published", pattern="^(pending|approved|rejected|published)$"),
    sort_by: str = Query("install_count", pattern="^(install_count|rating|created_at|name)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(AppPlugin)

    if status:
        query = query.where(AppPlugin.status == status)
    if category:
        query = query.where(AppPlugin.category == category)
    if search:
        query = query.where(
            AppPlugin.name.ilike(f"%{search}%") | AppPlugin.description.ilike(f"%{search}%")
        )

    total_result = await db.execute(select(sa_func.count()).select_from(query.subquery()))
    total = total_result.scalar()

    sort_column = getattr(AppPlugin, sort_by, AppPlugin.install_count)
    if order == "desc":
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()
    total_pages = (total + page_size - 1) // page_size

    return AppPluginListResponse(
        items=list(items),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/plugins/official")
async def list_official_plugins(
    current_user: User = Depends(get_current_user),
):
    """返回 Plugin SDK 注册表中的官方插件清单（id/name/description/category/version/config_schema）。"""
    items = []
    for p in sdk_list_plugins():
        items.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "category": p.category,
            "version": p.version,
            "config_schema": p.config_schema,
        })
    return {"items": items, "total": len(items)}


@router.get("/plugins/{plugin_id}", response_model=AppPluginResponse)
async def get_plugin_detail(
    plugin_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(AppPlugin).where(AppPlugin.id == plugin_id))
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")
    return plugin


@router.post("/plugins", response_model=AppPluginResponse)
async def create_plugin(
    data: AppPluginCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plugin = AppPlugin(
        name=data.name,
        description=data.description,
        icon=data.icon,
        version=data.version,
        author=data.author,
        category=data.category,
        status="pending",
        manifest=data.manifest.model_dump(),
        download_url=data.download_url,
        rating=0,
        install_count=0,
        created_by=current_user.id,
    )
    db.add(plugin)
    await db.commit()
    await db.refresh(plugin)
    return plugin


@router.post("/plugins/{plugin_id}/install", response_model=AppInstallationResponse)
async def install_plugin(
    plugin_id: str,
    data: PluginInstallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 官方 SDK 插件：注册表命中即可安装，无需市场 AppPlugin 行
    is_official = plugin_id in PLUGIN_REGISTRY
    if not is_official:
        result = await db.execute(select(AppPlugin).where(AppPlugin.id == plugin_id))
        plugin = result.scalar_one_or_none()
        if not plugin:
            raise HTTPException(status_code=404, detail="插件不存在")

    project_id = data.project_id
    # organization_id 为模型非空字段：未传组织时以 project_id 承载项目作用域
    org_id = data.organization_id or project_id or ""

    existing_result = await db.execute(
        select(AppInstallation).where(
            AppInstallation.plugin_id == plugin_id,
            AppInstallation.organization_id == org_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="该插件已安装")

    installation = AppInstallation(
        plugin_id=plugin_id,
        organization_id=org_id,
        project_id=project_id,
        config=data.config,
        status="active",
        installed_by=current_user.id,
    )
    db.add(installation)

    # 仅当存在市场插件行时才累加安装计数
    if not is_official:
        result = await db.execute(select(AppPlugin).where(AppPlugin.id == plugin_id))
        plugin = result.scalar_one_or_none()
        if plugin:
            plugin.install_count += 1

    await db.commit()
    await db.refresh(installation)

    response_data = AppInstallationResponse.model_validate(installation)
    if not is_official:
        result = await db.execute(select(AppPlugin).where(AppPlugin.id == plugin_id))
        plugin = result.scalar_one_or_none()
        if plugin:
            response_data.plugin = AppPluginResponse.model_validate(plugin)
    return response_data


@router.post("/plugins/{plugin_id}/execute")
async def execute_plugin(
    plugin_id: str,
    data: PluginExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按该项目的安装配置执行一次插件（body 含 project_id + 触发上下文）。"""
    plugin = get_plugin(plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="官方插件不存在或未注册")

    # 查找该项目下该插件的安装配置
    result = await db.execute(
        select(AppInstallation).where(
            AppInstallation.plugin_id == plugin_id,
            AppInstallation.project_id == data.project_id,
            AppInstallation.status == "active",
        )
    )
    installation = result.scalar_one_or_none()
    if not installation:
        raise HTTPException(status_code=404, detail="该项目未安装此插件或已禁用")

    context = dict(data.context or {})
    context.setdefault("project_id", data.project_id)
    context.setdefault("user_id", current_user.id)

    try:
        output = await plugin.execute(context, installation.config or {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"插件执行异常: {e}")

    return {
        "plugin_id": plugin_id,
        "project_id": data.project_id,
        "result": output,
    }


@router.post("/plugins/{plugin_id}/uninstall")
async def uninstall_plugin(
    plugin_id: str,
    organization_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AppInstallation).where(
            AppInstallation.plugin_id == plugin_id,
            AppInstallation.organization_id == organization_id,
        )
    )
    installation = result.scalar_one_or_none()
    if not installation:
        raise HTTPException(status_code=404, detail="安装记录不存在")

    plugin_result = await db.execute(select(AppPlugin).where(AppPlugin.id == plugin_id))
    plugin = plugin_result.scalar_one_or_none()
    if plugin and plugin.install_count > 0:
        plugin.install_count -= 1

    await db.delete(installation)
    await db.commit()
    return {"success": True, "message": "卸载成功"}


@router.post("/plugins/{plugin_id}/rate")
async def rate_plugin(
    plugin_id: str,
    data: PluginRateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(AppPlugin).where(AppPlugin.id == plugin_id))
    plugin = result.scalar_one_or_none()
    if not plugin:
        raise HTTPException(status_code=404, detail="插件不存在")

    plugin.rating = data.rating
    await db.commit()
    return {"success": True, "message": "评分成功"}


@router.get("/installed", response_model=AppInstallationListResponse)
async def list_installed_plugins(
    organization_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AppInstallation).where(
            AppInstallation.organization_id == organization_id,
            AppInstallation.status == "active",
        )
    )
    items = result.scalars().all()

    result_list = []
    for item in items:
        plugin_result = await db.execute(select(AppPlugin).where(AppPlugin.id == item.plugin_id))
        plugin = plugin_result.scalar_one_or_none()
        resp = AppInstallationResponse.model_validate(item)
        if plugin:
            resp.plugin = AppPluginResponse.model_validate(plugin)
        result_list.append(resp)

    return AppInstallationListResponse(items=result_list, total=len(result_list))


@router.put("/installations/{installation_id}/config", response_model=AppInstallationResponse)
async def update_installation_config(
    installation_id: str,
    data: AppInstallationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(AppInstallation).where(AppInstallation.id == installation_id))
    installation = result.scalar_one_or_none()
    if not installation:
        raise HTTPException(status_code=404, detail="安装记录不存在")

    if data.config is not None:
        installation.config = data.config
    if data.status is not None:
        installation.status = data.status

    await db.commit()
    await db.refresh(installation)

    plugin_result = await db.execute(select(AppPlugin).where(AppPlugin.id == installation.plugin_id))
    plugin = plugin_result.scalar_one_or_none()
    resp = AppInstallationResponse.model_validate(installation)
    if plugin:
        resp.plugin = AppPluginResponse.model_validate(plugin)
    return resp

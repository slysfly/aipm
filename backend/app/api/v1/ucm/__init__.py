"""用户管理子系统 (UCM) 路由聚合"""
from fastapi import APIRouter

from app.api.v1.ucm import organizations, catalog, billing, levels, dashboard, grants

router = APIRouter()
router.include_router(organizations.router, tags=["用户管理-组织"])
router.include_router(catalog.router, tags=["用户管理-套餐"])
router.include_router(billing.router, tags=["用户管理-收费"])
router.include_router(levels.router, tags=["用户管理-等级"])
router.include_router(dashboard.router, tags=["用户管理-看板"])
router.include_router(grants.router, tags=["用户管理-权限开通"])

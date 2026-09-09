"""
PMI中国AI项目管理社区 - 应用市场/插件生态 Pydantic Schemas
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class PluginManifest(BaseModel):
    """插件清单定义"""
    model_config = ConfigDict(from_attributes=True)

    entry_point: str = Field(..., description="插件入口文件路径")
    permissions: List[str] = Field(default_factory=list, description="所需权限列表")
    webhooks: List[Dict[str, Any]] = Field(default_factory=list, description="Webhook定义")
    config_schema: Dict[str, Any] = Field(default_factory=dict, description="配置JSON Schema")


class AppPluginBase(BaseModel):
    """插件基础Schema"""
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    icon: Optional[str] = None
    version: str = Field(..., max_length=50)
    author: str = Field(..., max_length=255)
    category: str = Field(default="utility", pattern="^(integration|automation|report|ai|utility)$")
    status: str = Field(default="pending", pattern="^(pending|approved|rejected|published)$")
    manifest: PluginManifest = Field(default_factory=lambda: PluginManifest(entry_point=""))
    download_url: Optional[str] = None
    rating: int = Field(default=0, ge=0, le=5)
    install_count: int = Field(default=0, ge=0)


class AppPluginCreate(AppPluginBase):
    """创建插件"""
    pass


class AppPluginUpdate(BaseModel):
    """更新插件"""
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    icon: Optional[str] = None
    version: Optional[str] = Field(None, max_length=50)
    author: Optional[str] = Field(None, max_length=255)
    category: Optional[str] = Field(None, pattern="^(integration|automation|report|ai|utility)$")
    status: Optional[str] = Field(None, pattern="^(pending|approved|rejected|published)$")
    manifest: Optional[PluginManifest] = None
    download_url: Optional[str] = None


class AppPluginResponse(AppPluginBase):
    """插件响应"""
    id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class AppPluginListResponse(BaseModel):
    """插件列表响应"""
    model_config = ConfigDict(from_attributes=True)

    items: List[AppPluginResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AppInstallationBase(BaseModel):
    """安装记录基础Schema"""
    model_config = ConfigDict(from_attributes=True)

    plugin_id: str
    organization_id: str
    project_id: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="active", pattern="^(active|disabled)$")


class AppInstallationCreate(AppInstallationBase):
    """创建安装记录"""
    pass


class AppInstallationUpdate(BaseModel):
    """更新安装记录"""
    model_config = ConfigDict(from_attributes=True)

    config: Optional[Dict[str, Any]] = None
    status: Optional[str] = Field(None, pattern="^(active|disabled)$")


class AppInstallationResponse(AppInstallationBase):
    """安装记录响应"""
    id: str
    installed_by: str
    installed_at: datetime
    plugin: Optional[AppPluginResponse] = None


class AppInstallationListResponse(BaseModel):
    """已安装插件列表响应"""
    model_config = ConfigDict(from_attributes=True)

    items: List[AppInstallationResponse]
    total: int


class PluginInstallRequest(BaseModel):
    """安装插件请求"""
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    project_id: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class PluginRateRequest(BaseModel):
    """评分请求"""
    model_config = ConfigDict(from_attributes=True)

    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class PluginSearchParams(BaseModel):
    """插件搜索参数"""
    model_config = ConfigDict(from_attributes=True)

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: Optional[str] = None
    category: Optional[str] = Field(None, pattern="^(integration|automation|report|ai|utility)$")
    status: Optional[str] = Field(default="published", pattern="^(pending|approved|rejected|published)$")
    sort_by: Optional[str] = Field(default="install_count", pattern="^(install_count|rating|created_at|name)$")
    order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$")

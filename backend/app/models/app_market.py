from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 应用市场/插件生态模型
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, JSON, Integer, ForeignKey, Index, Text
from sqlalchemy.sql import func

from app.db.session import Base


def generate_uuid():
    return str(uuid.uuid4())


class PluginCategory(str, enum.Enum):
    """插件分类枚举"""
    INTEGRATION = "integration"
    AUTOMATION = "automation"
    REPORT = "report"
    AI = "ai"
    UTILITY = "utility"


class PluginStatus(str, enum.Enum):
    """插件状态枚举"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class InstallationStatus(str, enum.Enum):
    """安装状态枚举"""
    ACTIVE = "active"
    DISABLED = "disabled"


class AppPlugin(Base):
    """应用市场插件模型"""
    __tablename__ = "app_plugins"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    icon = Column(String(500))
    version = Column(String(50), nullable=False)
    author = Column(String(255), nullable=False)
    category = Column(String(50), default=PluginCategory.UTILITY.value, index=True)
    status = Column(String(20), default=PluginStatus.PENDING.value, index=True)
    manifest = Column(JSON, default=dict)
    download_url = Column(String(500))
    rating = Column(Integer, default=0)
    install_count = Column(Integer, default=0)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    __table_args__ = (
        Index("ix_app_plugin_category_status", "category", "status"),
        Index("ix_app_plugin_author", "author"),
    )

    def __repr__(self):
        return f"<AppPlugin {self.name}@{self.version}>"


class AppInstallation(Base):
    """插件安装记录模型"""
    __tablename__ = "app_installations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    plugin_id = Column(String(36), ForeignKey("app_plugins.id"), nullable=False, index=True)
    organization_id = Column(String(36), nullable=False, index=True)
    # 项目级安装作用域（Plugin SDK 官方插件安装到项目时使用；市场插件可留空）
    project_id = Column(String(36), nullable=True, index=True)
    config = Column(JSON, default=dict)
    status = Column(String(20), default=InstallationStatus.ACTIVE.value, index=True)
    installed_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    installed_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    __table_args__ = (
        Index("ix_app_installation_org_plugin", "organization_id", "plugin_id", unique=True),
        Index("ix_app_installation_org_status", "organization_id", "status"),
    )

    def __repr__(self):
        return f"<AppInstallation plugin={self.plugin_id} org={self.organization_id}>"

from sqlalchemy import text
"""
PMI中国AI项目管理社区 - OpenClaw 配置持久化模型
替代原有的全局变量，将 OpenClaw 接入地址与开关存入数据库。
"""

from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class OpenClawConfig(Base):
    """OpenClaw 接入配置（系统级，仅一条生效记录）"""
    __tablename__ = "openclaw_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    base_url = Column(String(500), nullable=False, default="http://localhost:18888")
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "base_url": self.base_url,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<OpenClawConfig url={self.base_url} enabled={self.enabled}>"

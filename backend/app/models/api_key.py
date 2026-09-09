from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 对外 API Key 模型
供外部系统（含本地 OpenClaw）免登录调用本系统统一对外 API。
密钥以 SHA-256 哈希存储，仅展示前缀；按 scopes 限制读写权限。
"""

import secrets
import hashlib
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


def generate_api_key() -> str:
    """生成外部 API Key（格式 ak-<random>）。"""
    return "ak-" + secrets.token_urlsafe(28)


def hash_api_key(key: str) -> str:
    """对 API Key 做 SHA-256 哈希（用于安全存储与校验）。"""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class ApiKey(Base):
    __tablename__ = "api_keys"
    __model_config__ = {"protected_namespaces": ()}

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    # SHA-256 哈希（不存明文）
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    # 展示用前缀（前 12 位），便于管理员识别
    key_prefix = Column(String(16), nullable=False)
    # 权限范围，如 ["projects:read","tasks:write","ai:chat"]
    scopes = Column(JSON, default=list)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    def to_dict(self, include_key: bool = False) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "scopes": self.scopes or [],
            "is_active": self.is_active,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_key:
            data["plain_key"] = getattr(self, "_plain_key", None)
        return data

    def __repr__(self):
        return f"<ApiKey {self.name} {self.key_prefix}...>"

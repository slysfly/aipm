from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 系统级 LLM 默认配置模型
由管理员在"系统设置 > 大模型设置"中配置，作为全局 AI 能力的默认引擎。
API Key 使用 AES-256-GCM 加密存储（密文入库，明文不落库）。
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, Float, Text
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid
from app.core.encryption import encrypt_field, decrypt_field


class SystemLLMConfig(Base):
    """系统级 LLM 默认配置（全局唯一一条生效记录）"""

    __tablename__ = "system_llm_configs"
    __model_config__ = {"protected_namespaces": ()}

    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider_name = Column(String(50), nullable=False, index=True)
    _api_key = Column("api_key", Text, nullable=True)
    base_url = Column(String(500), nullable=True)
    model_name = Column(String(100), nullable=False)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2000)
    # 是否作为系统当前生效的默认大模型（全局 AI 能力使用它）
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    @property
    def api_key(self) -> str:
        if self._api_key:
            return decrypt_field(self._api_key)
        return ""

    @api_key.setter
    def api_key(self, value: str):
        if value:
            self._api_key = encrypt_field(value)
        else:
            self._api_key = None

    def to_dict(self, include_api_key: bool = False) -> dict:
        result = {
            "id": self.id,
            "provider_name": self.provider_name,
            "base_url": self.base_url,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            # 前端据此判断 api_key 是否已配置（不返回明文）
            "has_api_key": bool(self._api_key),
        }
        if include_api_key:
            result["api_key"] = self.api_key
        return result

    def __repr__(self):
        return f"<SystemLLMConfig {self.provider_name}/{self.model_name} active={self.is_active}>"

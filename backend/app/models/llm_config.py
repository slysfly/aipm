from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 用户级LLM配置模型
支持多Provider配置管理，API Key使用AES-256加密存储
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid
from app.core.encryption import encrypt_field, decrypt_field


class LLMConfig(Base):
    """用户级LLM配置模型"""
    __tablename__ = "llm_configs"
    __model_config__ = {"protected_namespaces": ()}

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    provider_name = Column(String(50), nullable=False, index=True)
    _api_key = Column("api_key", Text, nullable=True)
    base_url = Column(String(500), nullable=True)
    model_name = Column(String(100), nullable=False)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2000)
    is_default = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    user = relationship("User")

    @property
    def api_key(self) -> str:
        """获取解密后的API Key"""
        if self._api_key:
            return decrypt_field(self._api_key)
        return ""

    @api_key.setter
    def api_key(self, value: str):
        """设置加密后的API Key"""
        if value:
            self._api_key = encrypt_field(value)
        else:
            self._api_key = None

    def to_dict(self, include_api_key: bool = False) -> dict:
        """转换为字典"""
        result = {
            "id": self.id,
            "user_id": self.user_id,
            "provider_name": self.provider_name,
            "base_url": self.base_url,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "is_default": self.is_default,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_api_key:
            result["api_key"] = self.api_key
        return result

    def __repr__(self):
        return f"<LLMConfig {self.provider_name} user={self.user_id}>"

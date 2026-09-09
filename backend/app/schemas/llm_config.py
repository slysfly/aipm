"""
PMI中国AI项目管理社区 - LLM配置Pydantic Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class LLMConfigBase(BaseModel):
    """LLM配置基础模型"""
    provider_name: str = Field(..., min_length=1, max_length=50)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: str = Field(..., min_length=1, max_length=100)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=1, le=32000)
    is_enabled: bool = True

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class LLMConfigCreate(LLMConfigBase):
    """创建LLM配置"""
    pass


class LLMConfigUpdate(BaseModel):
    """更新LLM配置"""
    provider_name: Optional[str] = Field(None, min_length=1, max_length=50)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = Field(None, min_length=1, max_length=100)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)
    is_enabled: Optional[bool] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class LLMConfigResponse(BaseModel):
    """LLM配置响应"""
    id: str
    user_id: str
    provider_name: str
    base_url: Optional[str] = None
    model_name: str
    temperature: float
    max_tokens: int
    is_default: bool
    is_enabled: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class LLMConfigListResponse(BaseModel):
    """LLM配置列表响应"""
    items: List[LLMConfigResponse]
    total: int

    model_config = {"from_attributes": True}


class LLMProviderInfo(BaseModel):
    """LLM Provider信息"""
    name: str
    display_name: str
    description: str
    default_base_url: str
    default_model: str
    supported_models: List[str]
    requires_api_key: bool = True
    requires_secret: bool = False
    icon: Optional[str] = None
    config_advice: Optional[str] = None
    # AI 性价比推荐：每项 {"tag":"性价比首选|高性能|长文本|推理","model":"...","reason":"..."}
    # 前端按 tag 渲染为「AI 智能推荐」卡片，附一键填入按钮
    value_picks: List[Dict[str, str]] = Field(default_factory=list)
    # 该厂商是否兼容 OpenAI 协议并开放 /v1/models（false → 永远走静态 fallback）
    supports_models_endpoint: bool = True

    model_config = {"from_attributes": True}


class LLMProvidersResponse(BaseModel):
    """Provider列表响应"""
    providers: List[LLMProviderInfo]

    model_config = {"from_attributes": True}


class LLMConfigTestRequest(BaseModel):
    """测试LLM配置请求"""
    message: str = "Hello, this is a test message."

    model_config = {"from_attributes": True}


class LLMConfigTestResponse(BaseModel):
    """测试LLM配置响应"""
    success: bool
    message: str
    response: Optional[str] = None
    latency_ms: Optional[int] = None

    model_config = {"from_attributes": True}


class LLMConfigSetDefaultRequest(BaseModel):
    """设置默认配置请求"""
    pass

    model_config = {"from_attributes": True}

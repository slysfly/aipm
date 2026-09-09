"""
PMI中国AI项目管理社区 - 系统级 LLM 配置 Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class SystemLLMConfigUpsert(BaseModel):
    """创建 / 更新系统默认大模型配置"""

    provider_name: str = Field(..., min_length=1, max_length=50)
    api_key: Optional[str] = None  # 留空表示不修改已有 key
    base_url: Optional[str] = None
    model_name: str = Field(..., min_length=1, max_length=100)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=1, le=32000)
    is_active: bool = True

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class SystemLLMConfigResponse(BaseModel):
    id: str
    provider_name: str
    base_url: Optional[str] = None
    model_name: str
    temperature: float
    max_tokens: int
    is_active: bool
    has_api_key: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class SystemLLMConfigTestRequest(BaseModel):
    message: str = "你好，这是一次连接测试。"
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class SystemLLMConfigTestResponse(BaseModel):
    success: bool
    message: str
    response: Optional[str] = None
    latency_ms: Optional[int] = None
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class SystemLLMProviderInfo(BaseModel):
    """带配置建议的 provider 信息（复用用户级结构并补充 advice）"""

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
    value_picks: List[Dict[str, str]] = Field(default_factory=list)
    # 该厂商是否兼容 OpenAI 协议并开放 /v1/models（false → 永远走静态 fallback）
    supports_models_endpoint: bool = True

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class SystemLLMProvidersResponse(BaseModel):
    providers: List[SystemLLMProviderInfo]
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class SystemLLMFetchModelsRequest(BaseModel):
    """用 API Key 实时调厂商 /v1/models 拉取正在服务的模型清单

    - api_key 留空时后端会自动用系统已存的密文（推荐：UI 选择厂商时即触发，无需让用户重新粘贴）
    - base_url 留空时用 provider 的 default_base_url
    - force=True 时绕过本地周级缓存，强制实时拉取一次
    """

    provider_name: str = Field(..., min_length=1, max_length=50)
    base_url: Optional[str] = None
    api_key: Optional[str] = None  # 留空 → 用系统已存密文
    force: bool = False  # 默认优先读本地周级缓存
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class SystemLLMFetchModelsResponse(BaseModel):
    """实时拉取的模型列表 + 来源信息"""

    provider_name: str
    models: List[str]
    source: str = "live"  # "live" 实时 / "fallback" 厂商返回空时回退到静态
    raw_count: int = 0  # 厂商返回的原始 model 数量
    static_fallback: List[str] = []  # 回退时用的静态列表
    model_config = {"from_attributes": True, "protected_namespaces": ()}



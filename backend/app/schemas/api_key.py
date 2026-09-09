"""
PMI中国AI项目管理社区 - 对外 API Key Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    scopes: List[str] = Field(default_factory=list)
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: List[str] = []
    is_active: bool
    last_used_at: Optional[str] = None
    created_at: Optional[str] = None
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ApiKeyCreatedResponse(ApiKeyResponse):
    plain_key: str  # 仅在创建时一次性返回明文
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ExternalProjectCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    industry_type: Optional[str] = None
    priority: Optional[int] = 3
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ExternalTaskCreate(BaseModel):
    project_id: str
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    priority: Optional[int] = 3
    assignee_id: Optional[str] = None
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ExternalAssistantRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    project_id: Optional[str] = None
    model_config = {"from_attributes": True, "protected_namespaces": ()}

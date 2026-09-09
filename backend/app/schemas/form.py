"""
PMI中国AI项目管理社区 - 表单Schemas
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== 表单字段定义 ====================

class FormFieldValidation(BaseModel):
    """字段验证规则"""
    model_config = ConfigDict(from_attributes=True)

    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None
    custom_message: Optional[str] = None


class FormFieldOption(BaseModel):
    """字段选项"""
    model_config = ConfigDict(from_attributes=True)

    label: str
    value: str
    color: Optional[str] = None


class FormFieldDefinition(BaseModel):
    """表单字段定义"""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., min_length=1)
    type: str = Field(..., pattern="^(text|textarea|number|email|date|select|multiselect|checkbox|radio|file|rating|user_select|project_select)$")
    name: str = Field(..., min_length=1, max_length=100)
    label: str = Field(..., min_length=1, max_length=255)
    required: bool = False
    placeholder: Optional[str] = None
    help_text: Optional[str] = None
    options: List[FormFieldOption] = []
    validation: Optional[FormFieldValidation] = None
    default_value: Optional[Any] = None
    sort_order: int = 0


# ==================== 表单模板 ====================

class FormTemplateBase(BaseModel):
    """表单模板基础模型"""
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    fields: List[FormFieldDefinition] = []
    project_id: Optional[str] = None
    embed_in_task: bool = False
    embed_in_project: bool = False


class FormTemplateCreate(FormTemplateBase):
    """创建表单模板"""
    pass


class FormTemplateUpdate(BaseModel):
    """更新表单模板"""
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = None
    description: Optional[str] = None
    fields: Optional[List[FormFieldDefinition]] = None
    is_active: Optional[bool] = None
    is_published: Optional[bool] = None
    embed_in_task: Optional[bool] = None
    embed_in_project: Optional[bool] = None


class FormTemplateResponse(FormTemplateBase):
    """表单模板响应"""
    id: str
    created_by: str
    is_active: bool
    is_published: bool
    created_at: datetime
    updated_at: datetime


class FormTemplateListResponse(BaseModel):
    """表单模板列表响应"""
    model_config = ConfigDict(from_attributes=True)

    items: List[FormTemplateResponse]
    total: int


class FormTemplateStatsResponse(BaseModel):
    """表单模板统计响应"""
    model_config = ConfigDict(from_attributes=True)

    total_submissions: int
    pending_submissions: int
    approved_submissions: int
    rejected_submissions: int
    today_submissions: int
    weekly_submissions: int
    field_stats: List[Dict[str, Any]]


# ==================== 表单提交 ====================

class FormSubmissionBase(BaseModel):
    """表单提交基础模型"""
    model_config = ConfigDict(from_attributes=True)

    data: Dict[str, Any] = {}
    source_type: Optional[str] = None
    source_id: Optional[str] = None


class FormSubmissionCreate(FormSubmissionBase):
    """创建表单提交"""
    pass


class FormSubmissionUpdate(BaseModel):
    """更新表单提交"""
    model_config = ConfigDict(from_attributes=True)

    status: Optional[str] = None
    review_comment: Optional[str] = None


class FormSubmissionResponse(FormSubmissionBase):
    """表单提交响应"""
    id: str
    form_id: str
    submitted_by: str
    submitted_at: datetime
    status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comment: Optional[str] = None
    form_template: Optional[FormTemplateResponse] = None
    submitter: Optional[Dict[str, Any]] = None


class FormSubmissionListResponse(BaseModel):
    """表单提交列表响应"""
    model_config = ConfigDict(from_attributes=True)

    items: List[FormSubmissionResponse]
    total: int


class FormSubmissionDetailResponse(FormSubmissionResponse):
    """表单提交详情响应"""
    pass


# ==================== 表单嵌入 ====================

class FormEmbedRequest(BaseModel):
    """表单嵌入请求"""
    model_config = ConfigDict(from_attributes=True)

    source_type: str = Field(..., pattern="^(task|project)$")
    source_id: str


class FormEmbedResponse(BaseModel):
    """表单嵌入响应"""
    model_config = ConfigDict(from_attributes=True)

    form_id: str
    source_type: str
    source_id: str
    embed_url: str


# ==================== 数据导出 ====================

class FormExportRequest(BaseModel):
    """表单数据导出请求"""
    model_config = ConfigDict(from_attributes=True)

    format: str = Field(default="xlsx", pattern="^(xlsx|csv)$")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None

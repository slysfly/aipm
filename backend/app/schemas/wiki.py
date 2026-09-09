"""
PMI中国AI项目管理社区 - Wiki Pydantic Schemas
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime


class BaseSchema(BaseModel):
    """基础Schema"""
    model_config = ConfigDict(from_attributes=True)


# ==================== WikiSpace ====================

class WikiSpaceBase(BaseSchema):
    """知识空间基础模型"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    icon: str = "book"
    color: str = "#1890ff"
    is_public: bool = True


class WikiSpaceCreate(WikiSpaceBase):
    """创建知识空间"""
    member_ids: List[str] = []


class WikiSpaceUpdate(BaseSchema):
    """更新知识空间"""
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_public: Optional[bool] = None
    member_ids: Optional[List[str]] = None


class WikiSpaceResponse(WikiSpaceBase):
    """知识空间响应"""
    id: str
    owner_id: str
    member_ids: List[str] = []
    created_at: datetime
    updated_at: datetime


class WikiSpaceListResponse(BaseSchema):
    """知识空间列表响应"""
    items: List[WikiSpaceResponse]
    total: int


# ==================== WikiPage ====================

class WikiPageBase(BaseSchema):
    """页面基础模型"""
    title: str = Field(..., min_length=1, max_length=255)
    content: str = ""
    parent_id: Optional[str] = None
    order_index: int = 0


class WikiPageCreate(WikiPageBase):
    """创建页面"""
    space_id: str


class WikiPageUpdate(BaseSchema):
    """更新页面"""
    title: Optional[str] = None
    content: Optional[str] = None
    parent_id: Optional[str] = None
    order_index: Optional[int] = None


class WikiPageResponse(WikiPageBase):
    """页面响应"""
    id: str
    space_id: str
    created_by: str
    updated_by: Optional[str] = None
    version: int = 1
    is_locked: bool = False
    lock_by: Optional[str] = None
    lock_expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WikiPageTreeResponse(WikiPageResponse):
    """页面树形响应"""
    children: List["WikiPageTreeResponse"] = []


class WikiPageListResponse(BaseSchema):
    """页面列表响应"""
    items: List[WikiPageResponse]
    total: int


# ==================== WikiPageVersion ====================

class WikiPageVersionBase(BaseSchema):
    """版本历史基础模型"""
    title: str
    content: str = ""
    edit_summary: Optional[str] = None


class WikiPageVersionCreate(WikiPageVersionBase):
    """创建版本历史"""
    page_id: str
    editor_id: str


class WikiPageVersionResponse(WikiPageVersionBase):
    """版本历史响应"""
    id: str
    page_id: str
    editor_id: str
    created_at: datetime


class WikiPageVersionListResponse(BaseSchema):
    """版本历史列表响应"""
    items: List[WikiPageVersionResponse]
    total: int


# ==================== WikiComment ====================

class WikiCommentBase(BaseSchema):
    """评论基础模型"""
    content: str = Field(..., min_length=1)
    parent_id: Optional[str] = None


class WikiCommentCreate(WikiCommentBase):
    """创建评论"""
    page_id: str


class WikiCommentUpdate(BaseSchema):
    """更新评论"""
    content: Optional[str] = Field(None, min_length=1)


class WikiCommentAuthorInfo(BaseSchema):
    """评论作者信息"""
    id: str
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class WikiCommentResponse(WikiCommentBase):
    """评论响应"""
    id: str
    page_id: str
    author_id: str
    created_at: datetime
    updated_at: datetime
    author: Optional[WikiCommentAuthorInfo] = None
    replies: List["WikiCommentResponse"] = []


class WikiCommentListResponse(BaseSchema):
    """评论列表响应"""
    items: List[WikiCommentResponse]
    total: int


# ==================== Search ====================

class WikiSearchResult(BaseSchema):
    """搜索结果"""
    id: str
    title: str
    content_preview: str
    space_id: str
    space_name: str
    updated_at: datetime


class WikiSearchResponse(BaseSchema):
    """搜索响应"""
    items: List[WikiSearchResult]
    total: int
    query: str


# Forward reference update
WikiPageTreeResponse.model_rebuild()
WikiCommentResponse.model_rebuild()

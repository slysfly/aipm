"""
PMI中国AI项目管理社区 - Pydantic Schemas
用于API请求和响应的数据验证
"""

from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum


# ==================== 基础模型 ====================

class BaseSchema(BaseModel):
    """基础Schema"""
    model_config = ConfigDict(from_attributes=True)


class PageParams(BaseModel):
    """分页参数"""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: Optional[str] = None
    sort_by: Optional[str] = None
    order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$")


class PageResponse(BaseModel):
    """分页响应"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class SuccessResponse(BaseModel):
    """通用成功响应"""
    success: bool = True
    message: str = "操作成功"
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """通用错误响应"""
    success: bool = False
    error: Dict[str, Any]


# ==================== 用户相关 ====================

class UserBase(BaseSchema):
    """用户基础模型"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None


class UserCreate(UserBase):
    """创建用户"""
    password: str = Field(..., min_length=8)


class UserUpdate(BaseSchema):
    """更新用户"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """用户响应"""
    id: str
    avatar_url: Optional[str] = None
    is_active: bool
    is_superuser: bool
    last_login: Optional[datetime] = None
    created_at: datetime


class UserLogin(BaseSchema):
    """用户登录"""
    username: str
    password: str


class Token(BaseSchema):
    """Token响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseSchema):
    """Token载荷"""
    sub: str  # user_id
    exp: int
    type: str  # access/refresh


# ==================== 项目相关 ====================

class ProjectBase(BaseSchema):
    """项目基础模型"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    industry_type: str = "it_software"
    project_type: str = "agile"
    priority: int = Field(default=3, ge=1, le=5)
    color: str = "#1890ff"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: float = 0


class ProjectCreate(ProjectBase):
    """创建项目"""
    baseline_start: Optional[date] = None
    baseline_end: Optional[date] = None
    baseline_budget: Optional[float] = None
    portfolio_id: Optional[str] = None
    owner_id: Optional[str] = None


class ProjectUpdate(BaseSchema):
    """更新项目"""
    name: Optional[str] = None
    description: Optional[str] = None
    industry_type: Optional[str] = None
    project_type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    color: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    baseline_start: Optional[date] = None
    baseline_end: Optional[date] = None
    budget: Optional[float] = None
    baseline_budget: Optional[float] = None
    owner_id: Optional[str] = None


class ProjectResponse(ProjectBase):
    """项目响应"""
    id: str
    status: str
    owner_id: str
    portfolio_id: Optional[str] = None
    baseline_start: Optional[date] = None
    baseline_end: Optional[date] = None
    baseline_budget: Optional[float] = None
    actual_cost: float = 0
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime
    owner: Optional[UserResponse] = None
    
    # 统计字段
    task_count: int = 0
    completed_task_count: int = 0
    overdue_task_count: int = 0
    risk_count: int = 0


class ProjectListResponse(PageResponse):
    """项目列表响应"""
    items: List[ProjectResponse]


# ==================== 任务相关 ====================

class TaskBase(BaseSchema):
    """任务基础模型"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    estimated_hours: float = 0
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    priority: int = Field(default=3, ge=1, le=5)
    labels: List[str] = []
    category: Optional[str] = None
    sprint_id: Optional[str] = None  # 所属 Sprint（一对一归属）


class TaskCreate(TaskBase):
    """创建任务"""
    project_id: str
    parent_task_id: Optional[str] = None
    status: str = "todo"
    assignee_id: Optional[str] = None
    is_milestone: bool = False


class TaskUpdate(BaseSchema):
    """更新任务"""
    name: Optional[str] = None
    description: Optional[str] = None
    parent_task_id: Optional[str] = None
    estimated_hours: Optional[float] = None
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    progress: Optional[float] = Field(default=None, ge=0, le=100)
    status: Optional[str] = None
    priority: Optional[int] = None
    assignee_id: Optional[str] = None
    labels: Optional[List[str]] = None
    category: Optional[str] = None
    sprint_id: Optional[str] = None  # 支持变更/清空（None 表示不归属）


class TaskBriefResponse(TaskBase):
    """任务简版响应（不含递归 subtasks/dependencies，避免 async 上下文 lazy load）

    说明：
    - TaskResponse.subtasks 自引用导致 Pydantic 序列化时逐层访问 ORM 属性
    - 子对象若未 selectinload，访问 .subtasks/.dependencies_from 会触发 lazy load
    - async 上下文中 lazy load 抛 MissingGreenlet → FastAPI ResponseValidationError 500
    - 因此子任务用本简版，序列化时不再访问子对象的 subtasks/dependencies 属性
    """
    id: str
    project_id: str
    parent_task_id: Optional[str] = None
    wbs_code: Optional[str] = None
    level: int = 0
    sprint_id: Optional[str] = None
    actual_hours: float = 0
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    progress: float = 0
    status: str
    is_milestone: bool = False
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime
    # 不含 assignee/subtasks/dependencies 关系字段，避免 async lazy load MissingGreenlet
    assignee_id: Optional[str] = None
    planned_value: float = 0
    earned_value: float = 0
    actual_cost: float = 0
    # AI 下一步建议（保留，便于子任务面板/列表渲染）
    next_action_suggestion: Optional[Dict[str, Any]] = None
    next_action_generated_at: Optional[datetime] = None


class TaskResponse(TaskBase):
    """任务响应（顶层，含递归子任务；子任务序列化为 TaskBriefResponse 防止 lazy load 爆栈）"""
    id: str
    project_id: str
    parent_task_id: Optional[str] = None
    wbs_code: Optional[str] = None
    level: int = 0
    sprint_id: Optional[str] = None  # 所属 Sprint
    actual_hours: float = 0
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    progress: float = 0
    status: str
    assignee_id: Optional[str] = None
    is_milestone: bool = False
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime
    assignee: Optional[UserResponse] = None
    subtasks: List[TaskBriefResponse] = []
    dependencies: List["TaskDependencyResponse"] = Field(default=[], validation_alias="dependencies_from")

    # EVM字段
    planned_value: float = 0
    earned_value: float = 0
    actual_cost: float = 0

    # ── AI 下一步行动建议（自动生成） ──────────────────────────────────
    next_action_suggestion: Optional[Dict[str, Any]] = None
    next_action_generated_at: Optional[datetime] = None


class TaskListResponse(PageResponse):
    """任务列表响应"""
    items: List[TaskResponse]


# ==================== 任务依赖 ====================

class TaskDependencyBase(BaseSchema):
    """任务依赖基础模型"""
    predecessor_id: str
    successor_id: str
    dependency_type: str = "FS"
    lag_time: int = 0


class TaskDependencyCreate(TaskDependencyBase):
    """创建任务依赖"""
    pass


class TaskDependencyResponse(TaskDependencyBase):
    """任务依赖响应"""
    id: str
    created_at: datetime


# ==================== Portfolio ====================

class PortfolioBase(BaseSchema):
    """Portfolio基础模型"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    strategic_goals: List[Dict[str, Any]] = []


class PortfolioCreate(PortfolioBase):
    """创建Portfolio"""
    owner_id: Optional[str] = None


class PortfolioUpdate(BaseSchema):
    """更新Portfolio"""
    name: Optional[str] = None
    description: Optional[str] = None
    strategic_goals: Optional[List[Dict[str, Any]]] = None


class PortfolioResponse(PortfolioBase):
    """Portfolio响应"""
    id: str
    owner_id: str
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime
    owner: Optional[UserResponse] = None
    project_count: int = 0


# ==================== 资源管理 ====================

class ResourceBase(BaseSchema):
    """资源基础模型"""
    name: str = Field(..., min_length=1, max_length=255)
    resource_type: str = "person"
    skills: List[str] = []
    capacity: float = 8.0
    cost_rate: float = 0
    department: Optional[str] = None


class ResourceCreate(ResourceBase):
    """创建资源"""
    user_id: Optional[str] = None


class ResourceUpdate(BaseSchema):
    """更新资源"""
    name: Optional[str] = None
    resource_type: Optional[str] = None
    skills: Optional[List[str]] = None
    capacity: Optional[float] = None
    cost_rate: Optional[float] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None


class ResourceResponse(ResourceBase):
    """资源响应"""
    id: str
    user_id: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    user: Optional[UserResponse] = None


class ResourceAllocationCreate(BaseSchema):
    """创建资源分配"""
    task_id: str
    resource_id: str
    allocated_hours: float
    allocated_date: date


class ResourceAllocationResponse(BaseSchema):
    """资源分配响应"""
    id: str
    task_id: str
    resource_id: str
    project_id: str
    allocated_hours: float
    allocated_date: date
    resource: ResourceResponse


# ==================== 风险管理 ====================

class RiskBase(BaseSchema):
    """风险基础模型"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = "technical"
    probability: float = Field(default=0.5, ge=0, le=1)
    impact: float = Field(default=0.5, ge=0, le=1)
    trigger_condition: Optional[str] = None
    response_strategy: Optional[str] = None
    response_plan: Optional[str] = None
    response_cost: float = 0


class RiskCreate(RiskBase):
    """创建风险"""
    project_id: str
    owner_id: Optional[str] = None


class RiskUpdate(BaseSchema):
    """更新风险"""
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    probability: Optional[float] = None
    impact: Optional[float] = None
    trigger_condition: Optional[str] = None
    status: Optional[str] = None
    owner_id: Optional[str] = None
    response_strategy: Optional[str] = None
    response_plan: Optional[str] = None
    response_cost: Optional[float] = None


class RiskResponse(RiskBase):
    """风险响应"""
    id: str
    project_id: str
    risk_score: float
    status: str
    owner_id: Optional[str] = None
    identified_at: Optional[datetime] = None
    occurred_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    ai_analysis: Optional[Dict] = None
    created_at: datetime
    updated_at: datetime
    owner: Optional[UserResponse] = None


# ==================== EVM挣值管理 ====================

class EVMSnapshotBase(BaseSchema):
    """EVM快照基础模型"""
    snapshot_date: date


class EVMSnapshotCreate(EVMSnapshotBase):
    """创建EVM快照"""
    project_id: str
    planned_value: float = 0
    earned_value: float = 0
    actual_cost: float = 0


class EVMSnapshotResponse(EVMSnapshotBase):
    """EVM快照响应"""
    id: str
    project_id: str
    planned_value: float
    earned_value: float
    actual_cost: float
    cost_variance: float
    schedule_variance: float
    cost_performance_index: float
    schedule_performance_index: float
    estimate_at_completion: float
    estimate_to_complete: float
    variance_at_completion: float
    to_complete_performance_index: float
    ai_predictions: Optional[Dict] = None
    created_at: datetime


# ==================== 甘特图 ====================

class GanttTaskResponse(BaseSchema):
    """甘特图任务响应"""
    id: str
    wbs_code: Optional[str] = None
    name: str
    level: int
    status: str
    priority: int
    assignee_id: Optional[str] = None
    assignee_name: Optional[str] = None
    planned_start: Optional[datetime] = None
    planned_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    progress: float
    is_milestone: bool
    dependencies: List[Dict] = []
    children: List["GanttTaskResponse"] = []


class CriticalPathResponse(BaseSchema):
    """关键路径响应"""
    critical_path: List[str]  # 任务ID列表
    total_duration: int  # 总工期（天）
    milestones: List[Dict]  # 里程碑列表


# ==================== AI能力 ====================

class NaturalLanguageInput(BaseSchema):
    """自然语言输入"""
    text: str = Field(..., min_length=10)
    project_id: Optional[str] = None
    context: Dict[str, Any] = {}


class WBSGenerationRequest(BaseSchema):
    """WBS生成请求

    通过自然语言描述项目，AI 自动生成完整 WBS（含估算/风险/资源建议）。
    触发后返回 task_id，可通过 WebSocket 实时接收生成进度，
    或轮询 GET /async-tasks/{task_id} 获取结果。
    """
    project_name: str = Field(..., description="项目名称（必填）", examples=["新一代 ERP 系统建设"])
    project_description: str = Field("", description="项目描述/背景/目标，越详细生成质量越高", examples=["建设一套覆盖集团财务/HR/供应链的 ERP 系统，预算 500 万，工期 12 个月"])
    industry_type: str = Field("it_software", description="行业类型，可选：it_software/manufacturing/construction/education/finance/government", examples=["it_software"])
    constraints: Dict[str, Any] = Field(default_factory=dict, description="约束条件：预算/工期/团队规模/技术栈等", examples=[{"budget": 5000000, "duration_months": 12, "team_size": 15}])
    project_id: Optional[str] = Field(None, description="关联项目 ID。若提供且 save_to_tasks=true，则将生成的 WBS 直接回写为该项目下的任务", examples=["39a0114c-4a10-46a2-988a-223a7f4a112f"])
    save_to_tasks: bool = Field(False, description="是否将生成的 WBS 自动回写为项目任务（需同时提供 project_id）", examples=[True])
    kb_id: Optional[str] = Field(None, description="参照的知识库 ID。为空时系统默认使用可访问的公开知识库；也可传入本人私密知识库 ID。AI 生成将首先参照该知识库沉淀（公开/私密二选一，不可同时使用）", examples=["39a0114c-4a10-46a2-988a-223a7f4a112f"])


class WBSGenerationResponse(BaseSchema):
    """WBS生成响应"""
    project_intent: Dict[str, Any]  # 解析的项目意图
    wbs_structure: List[Dict[str, Any]]  # WBS结构
    milestones: List[Dict[str, Any]]  # 建议的里程碑
    resource_requirements: List[Dict[str, Any]]  # 资源需求
    risk_identification: List[Dict[str, Any]]  # 识别的风险
    confidence_score: float  # 置信度
    suggestions: List[str]  # 优化建议


class AIChatRequest(BaseSchema):
    """AI对话请求"""
    message: str
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    kb_id: Optional[str] = Field(None, description="知识库 ID。传入后 AI 将优先依据该知识库（私密库限本人）的内容作答，用于个人知识问答", examples=[None])


class AIChatResponse(BaseSchema):
    """AI对话响应"""
    message: str
    suggested_actions: List[Dict[str, Any]] = []
    related_tasks: List[str] = []
    confidence: float


# ==================== 评论相关 ====================

class CommentBase(BaseSchema):
    """评论基础模型"""
    content: str = Field(..., min_length=1)
    mentions: List[str] = []


class CommentCreate(CommentBase):
    """创建评论"""
    task_id: str
    project_id: Optional[str] = None
    parent_id: Optional[str] = None


class CommentUpdate(BaseSchema):
    """更新评论"""
    content: Optional[str] = Field(None, min_length=1)
    mentions: Optional[List[str]] = None


class CommentUserInfo(BaseSchema):
    """评论用户信息"""
    id: str
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class CommentResponse(BaseSchema):
    """评论响应"""
    id: str
    content: str
    task_id: str
    project_id: Optional[str] = None
    user_id: str
    parent_id: Optional[str] = None
    mentions: List[str] = []
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime
    user: Optional[CommentUserInfo] = None
    replies: List["CommentResponse"] = []


class CommentListResponse(PageResponse):
    """评论列表响应"""
    items: List[CommentResponse]


# ==================== 通知相关 ====================

class NotificationBase(BaseSchema):
    """通知基础模型"""
    type: str
    title: str
    content: Optional[str] = None
    related_type: Optional[str] = None
    related_id: Optional[str] = None


class NotificationCreate(NotificationBase):
    """创建通知"""
    user_id: str


class NotificationUpdate(BaseSchema):
    """更新通知"""
    is_read: Optional[bool] = None


class NotificationResponse(BaseSchema):
    """通知响应"""
    id: str
    user_id: str
    type: str
    title: str
    content: Optional[str] = None
    related_type: Optional[str] = None
    related_id: Optional[str] = None
    is_read: bool = False
    read_at: Optional[datetime] = None
    created_at: datetime


class NotificationListResponse(PageResponse):
    """通知列表响应"""
    items: List[NotificationResponse]


class UnreadCountResponse(BaseSchema):
    """未读数量响应"""
    count: int


# ==================== 附件相关 ====================

class AttachmentBase(BaseSchema):
    """附件基础模型"""
    filename: str
    original_name: str
    file_size: int
    mime_type: str


class AttachmentCreate(AttachmentBase):
    """创建附件"""
    file_path: str
    task_id: Optional[str] = None
    project_id: Optional[str] = None
    comment_id: Optional[str] = None
    uploaded_by: str


class AttachmentResponse(BaseSchema):
    """附件响应"""
    id: str
    filename: str
    original_name: str
    file_path: str
    file_size: int
    mime_type: str
    task_id: Optional[str] = None
    project_id: Optional[str] = None
    comment_id: Optional[str] = None
    uploaded_by: str
    created_at: datetime


class AttachmentListResponse(PageResponse):
    """附件列表响应"""
    items: List[AttachmentResponse]


# ==================== 消息相关 ====================

from app.schemas.message import (
    MessageBase, MessageCreate, MessageUpdate, MessageResponse, MessageListResponse,
    MessageSenderInfo, MessageReactionInfo,
    ChannelBase, ChannelCreate, ChannelUpdate, ChannelResponse, ChannelListResponse,
    ChannelMemberInfo, ReactionCreate, ReadMarkerUpdate,
)

from app.schemas.recurring_task import (
    RecurringTaskBase, RecurringTaskCreate, RecurringTaskUpdate,
    RecurringTaskResponse, RecurringTaskListResponse,
    RecurringTaskInstanceResponse, RecurringTaskInstanceListResponse,
    RecurringTaskToggleResponse, RecurringTaskRunNowResponse,
    RecurringTaskPreviewResponse,
)

from app.schemas.compliance import (
    CompliancePolicyCreate, CompliancePolicyUpdate, CompliancePolicyResponse,
    CompliancePolicyListResponse,
    ComplianceControlCreate, ComplianceControlUpdate, ComplianceControlResponse,
    ComplianceControlListResponse, ControlTestRequest, ControlTestResponse,
    ComplianceAuditCreate, ComplianceAuditResponse, ComplianceAuditListResponse,
    ComplianceEvidenceCreate, ComplianceEvidenceResponse,
    ComplianceEvidenceListResponse,
    ComplianceDashboardResponse, ComplianceSummaryReportResponse,
)

from app.schemas.app_market import (
    AppPluginCreate, AppPluginUpdate, AppPluginResponse, AppPluginListResponse,
    AppInstallationCreate, AppInstallationUpdate, AppInstallationResponse, AppInstallationListResponse,
    PluginInstallRequest, PluginRateRequest, PluginManifest,
)

# Forward reference update
TaskResponse.model_rebuild()
GanttTaskResponse.model_rebuild()
CommentResponse.model_rebuild()
MessageResponse.model_rebuild()
ChannelResponse.model_rebuild()

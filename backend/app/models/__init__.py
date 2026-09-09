from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 数据模型
包含所有核心实体的数据库模型
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Enum, Text, JSON, Numeric, Date, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.db.session import Base


def generate_uuid():
    """生成UUID"""
    return str(uuid.uuid4())


class User(Base):
    """用户模型"""
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    avatar_url = Column(String(500))
    phone = Column(String(20))
    department = Column(String(100))
    position = Column(String(100))
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    last_login = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 用户管理子系统扩展字段
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)  # 主组织
    level_code = Column(String(20), default="free", index=True)  # 用户等级
    level_points = Column(Integer, default=0)  # 等级积分
    is_org_admin = Column(Boolean, default=False)  # 是否租户管理员

    # 关系
    owned_projects = relationship("Project", back_populates="owner", foreign_keys="Project.owner_id")
    assigned_tasks = relationship("Task", back_populates="assignee", foreign_keys="Task.assignee_id")
    owned_risks = relationship("Risk", back_populates="owner", foreign_keys="Risk.owner_id")
    
    def __repr__(self):
        try:
            return f"<User {self.username}>"
        except Exception:
            return "<User ?(detached)>"


class ProjectStatus(str, enum.Enum):
    """项目状态枚举"""
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class IndustryType(str, enum.Enum):
    """行业类型枚举"""
    IT_SOFTWARE = "it_software"
    IT_HARDWARE = "it_hardware"
    CONSTRUCTION = "construction"
    MANUFACTURING = "manufacturing"
    SERVICE = "service"
    CONSULTING = "consulting"
    EDUCATION = "education"
    HEALTHCARE = "healthcare"
    FINANCE = "finance"
    OTHER = "other"


class ProjectTypeEnum(str, enum.Enum):
    """项目类型枚举（历史兼容，已被可自定义 project_types 表取代）"""
    AGILE = "agile"
    WATERFALL = "waterfall"
    HYBRID = "hybrid"
    KANBAN = "kanban"


class Project(Base):
    """项目模型"""
    __tablename__ = "projects"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    industry_type = Column(String(50), default=IndustryType.IT_SOFTWARE.value)
    project_type = Column(String(50), default="agile")  # 引用 project_types.code（可自定义）
    status = Column(String(20), default=ProjectStatus.PLANNING.value, index=True)
    priority = Column(Integer, default=3)  # 1-5, 1最高
    color = Column(String(7), default="#1890ff")  # Hex color
    
    # 日期
    start_date = Column(Date)
    end_date = Column(Date)
    baseline_start = Column(Date)  # 基线开始
    baseline_end = Column(Date)  # 基线结束
    
    # 财务
    budget = Column(Numeric(15, 2), default=0)
    baseline_budget = Column(Numeric(15, 2), default=0)
    actual_cost = Column(Numeric(15, 2), default=0)
    
    # 外键
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    portfolio_id = Column(String(36), ForeignKey("portfolios.id"), nullable=True)
    
    # 配置
    settings = Column(JSON, default=dict)  # 项目自定义设置
    
    # 软删除
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime(timezone=True))
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    
    # 关系
    owner = relationship("User", back_populates="owned_projects", foreign_keys=[owner_id])
    portfolio = relationship("Portfolio", back_populates="projects")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    risks = relationship("Risk", back_populates="project", cascade="all, delete-orphan")
    milestones = relationship("Milestone", back_populates="project", cascade="all, delete-orphan")
    resources = relationship("ResourceAllocation", back_populates="project")
    evm_snapshots = relationship("EVMSnapshot", back_populates="project", cascade="all, delete-orphan")
    
    # 索引
    __table_args__ = (
        Index("ix_project_status_priority", "status", "priority"),
        Index("ix_project_owner_status", "owner_id", "status"),
        Index("ix_project_dates", "start_date", "end_date"),
    )
    
    def __repr__(self):
        return f"<Project {self.name}>"


class TaskStatus(str, enum.Enum):
    """任务状态枚举"""
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    TESTING = "testing"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(int, enum.Enum):
    """任务优先级枚举"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    LOWEST = 5


class Task(Base):
    """任务模型"""
    __tablename__ = "tasks"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    parent_task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True)  # 层级关系
    wbs_code = Column(String(50), index=True)  # WBS编码，如 "1.1.2"
    # 任务→Sprint 一对一归属：哪个迭代中执行；与 sprint_tasks N:N 表并存兼容
    sprint_id = Column(String(36), ForeignKey("sprints.id"), nullable=True, index=True)
    
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    level = Column(Integer, default=0)  # 层级深度
    estimated_hours = Column(Numeric(10, 2), default=0)
    actual_hours = Column(Numeric(10, 2), default=0)
    
    # 日期
    planned_start = Column(DateTime(timezone=True))
    planned_end = Column(DateTime(timezone=True))
    actual_start = Column(DateTime(timezone=True))
    actual_end = Column(DateTime(timezone=True))
    
    # 进度
    progress = Column(Numeric(5, 2), default=0)  # 0-100
    
    # 状态
    status = Column(String(20), default=TaskStatus.TODO.value, index=True)
    priority = Column(Integer, default=TaskPriority.MEDIUM.value)
    
    # 负责人
    assignee_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    is_milestone = Column(Boolean, default=False)
    
    # 分类
    labels = Column(JSON, default=list)  # 标签列表
    category = Column(String(50))  # 任务类别
    
    # 估算数据（用于EVM）
    planned_value = Column(Numeric(15, 2), default=0)  # PV
    earned_value = Column(Numeric(15, 2), default=0)  # EV
    actual_cost = Column(Numeric(15, 2), default=0)  # AC
    
    # 排序
    sort_order = Column(Integer, default=0)
    
    # 软删除
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime(timezone=True))
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 乐观锁版本号：每次更新自增；离线编辑回放时携带 X-Base-Version，
    # 与服务端不一致则 409 冲突，交由前端冲突合并流程处理。
    version = Column(Integer, default=1, nullable=False)

    # ── AI 下一步行动建议（规则引擎自动生成） ──────────────────────────
    # 当任务被创建/状态/进度/截止/负责人等关键维度变更时自动重新生成。
    # next_action_suggestion 结构：
    #   {
    #     "summary": "一句话结论",
    #     "scenario": "overdue|behind|cost_overrun|no_assignee|stalled|in_review|testing|done|idle",
    #     "items": [{"action": "...", "reason": "...", "priority": 1-3, "eta": "今天/本周/..."}],
    #     "confidence": 0.0-1.0,
    #   }
    next_action_suggestion = Column(JSON, nullable=True)
    next_action_generated_at = Column(DateTime(timezone=True), nullable=True)
    # 用于变更检测的字段指纹（由 next_action_service 计算）
    next_action_source_hash = Column(String(64), nullable=True)

    # 关系
    project = relationship("Project", back_populates="tasks")
    parent_task = relationship("Task", remote_side=[id], backref="subtasks")
    assignee = relationship("User", back_populates="assigned_tasks", foreign_keys=[assignee_id])
    dependencies_from = relationship(
        "TaskDependency",
        foreign_keys="TaskDependency.successor_id",
        back_populates="successor",
        cascade="all, delete-orphan"
    )
    dependencies_to = relationship(
        "TaskDependency",
        foreign_keys="TaskDependency.predecessor_id",
        back_populates="predecessor",
        cascade="all, delete-orphan"
    )
    comments = relationship("Comment", back_populates="task", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="task", cascade="all, delete-orphan")
    
    # 索引
    __table_args__ = (
        Index("ix_task_project_status", "project_id", "status"),
        Index("ix_task_assignee_status", "assignee_id", "status"),
        Index("ix_task_dates", "planned_start", "planned_end"),
        Index("ix_task_wbs", "wbs_code"),
    )
    
    def __repr__(self):
        d = self.__dict__
        return f"<Task {d.get('wbs_code')} {d.get('name')}>"


class DependencyType(str, enum.Enum):
    """依赖类型枚举"""
    FS = "FS"  # Finish to Start
    FF = "FF"  # Finish to Finish
    SS = "SS"  # Start to Start
    SF = "SF"  # Start to Finish


class TaskDependency(Base):
    """任务依赖模型"""
    __tablename__ = "task_dependencies"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    predecessor_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    successor_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    dependency_type = Column(String(2), default=DependencyType.FS.value)
    lag_time = Column(Integer, default=0)  # 延迟天数，正值延迟，负值提前
    
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    
    # 关系
    predecessor = relationship("Task", foreign_keys=[predecessor_id], back_populates="dependencies_from")
    successor = relationship("Task", foreign_keys=[successor_id], back_populates="dependencies_to")
    
    # 约束
    __table_args__ = (
        Index("ix_dependency_unique", "predecessor_id", "successor_id", unique=True),
    )
    
    def __repr__(self):
        return f"<TaskDependency {self.predecessor_id} -> {self.successor_id}>"


class Portfolio(Base):
    """项目组合模型"""
    __tablename__ = "portfolios"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    strategic_goals = Column(JSON, default=list)  # 战略目标列表
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    
    # 配置
    settings = Column(JSON, default=dict)
    
    # 软删除
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    
    # 关系
    owner = relationship("User")
    projects = relationship("Project", back_populates="portfolio")
    
    def __repr__(self):
        return f"<Portfolio {self.name}>"


class ResourceType(str, enum.Enum):
    """资源类型枚举"""
    PERSON = "person"
    EQUIPMENT = "equipment"
    MATERIAL = "material"
    BUDGET = "budget"


class Resource(Base):
    """资源模型"""
    __tablename__ = "resources"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False, index=True)
    resource_type = Column(String(20), default=ResourceType.PERSON.value)
    skills = Column(JSON, default=list)  # 技能列表
    capacity = Column(Numeric(10, 2), default=8.0)  # 日产能
    cost_rate = Column(Numeric(10, 2), default=0)  # 单位成本
    department = Column(String(100))
    avatar_url = Column(String(500))
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    
    # 关系
    user = relationship("User")
    allocations = relationship("ResourceAllocation", back_populates="resource")
    
    def __repr__(self):
        return f"<Resource {self.name}>"


class ResourceAllocation(Base):
    """资源分配模型

    支持两种录入语义（向后兼容）：
    - 旧式（单日）：task_id(必填) + allocated_date + allocated_hours
    - 新式（日期范围 + 每日工时）：start_date + end_date + hours_per_day
      可选 daily_hours JSON 覆盖 {"YYYY-MM-DD": hours}；task_id 可为空（自由文本任务），
      此时必须填 task_title。

    AI 优化：
    - is_ai_move=True 表示该条是 AI 调整过的，original_* 记录调整前的状态，便于撤销。
    """
    __tablename__ = "resource_allocations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    resource_id = Column(String(36), ForeignKey("resources.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)

    # ── 旧式单日字段（保留兼容） ─────────────────────────────────────────
    allocated_hours = Column(Numeric(10, 2), default=0)
    allocated_date = Column(Date)

    # ── 新式日期范围 + 每日工时（推荐） ──────────────────────────────────
    task_title = Column(String(255), default="")
    start_date = Column(Date, index=True)
    end_date = Column(Date, index=True)
    hours_per_day = Column(Numeric(10, 2), default=0)
    daily_hours = Column(JSON, default=dict)  # {"YYYY-MM-DD": hours} 覆盖 hours_per_day

    # ── 排程属性 ────────────────────────────────────────────────────────
    priority = Column(Integer, default=3)  # 1=紧急 5=最低
    status = Column(String(20), default="planned")  # planned/in_progress/done
    notes = Column(Text, default="")

    # ── AI 优化痕迹（is_ai_move=True 时，original_* 记录调整前快照） ──────
    is_ai_move = Column(Boolean, default=False)
    original_start_date = Column(Date)
    original_end_date = Column(Date)
    original_daily_hours = Column(JSON)
    original_hours_per_day = Column(Numeric(10, 2))
    optimization_reason = Column(String(512), default="")

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    task = relationship("Task")
    resource = relationship("Resource", back_populates="allocations")
    project = relationship("Project", back_populates="resources")

    # 索引
    __table_args__ = (
        Index("ix_alloc_resource_start", "resource_id", "start_date"),
        Index("ix_alloc_project_date", "project_id", "start_date"),
    )

    def __repr__(self):
        return f"<ResourceAllocation resource={self.resource_id} {self.start_date}~{self.end_date} {self.hours_per_day}h/d>"


class RiskStatus(str, enum.Enum):
    """风险状态枚举"""
    IDENTIFIED = "identified"
    ANALYZING = "analyzing"
    MITIGATING = "mitigating"
    OCCURRED = "occurred"
    CLOSED = "closed"


class RiskCategory(str, enum.Enum):
    """风险类别枚举"""
    TECHNICAL = "technical"
    SCHEDULE = "schedule"
    COST = "cost"
    RESOURCE = "resource"
    QUALITY = "quality"
    EXTERNAL = "external"
    BUSINESS = "business"


class Risk(Base):
    """风险模型"""
    __tablename__ = "risks"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    category = Column(String(20), default=RiskCategory.TECHNICAL.value)
    
    # 量化数据
    probability = Column(Numeric(5, 4), default=0.5)  # 0-1
    impact = Column(Numeric(5, 4), default=0.5)  # 0-1
    risk_score = Column(Numeric(10, 4))  # = probability * impact
    
    # 触发条件
    trigger_condition = Column(Text)
    
    # 状态
    status = Column(String(20), default=RiskStatus.IDENTIFIED.value)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    # 响应策略
    response_strategy = Column(String(50))  # avoid/mitigate/transfer/accept
    response_plan = Column(Text)
    response_cost = Column(Numeric(15, 2), default=0)
    
    # 时间
    identified_at = Column(DateTime(timezone=True))
    occurred_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))
    
    # AI分析
    ai_analysis = Column(JSON)  # AI风险分析结果
    
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    
    # 关系
    project = relationship("Project", back_populates="risks")
    owner = relationship("User", back_populates="owned_risks", foreign_keys=[owner_id])
    
    def __repr__(self):
        return f"<Risk {self.name}>"


class EVMSnapshot(Base):
    """EVM快照模型"""
    __tablename__ = "evm_snapshots"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)
    
    # EVM基础指标
    planned_value = Column(Numeric(15, 2), default=0)  # PV
    earned_value = Column(Numeric(15, 2), default=0)  # EV
    actual_cost = Column(Numeric(15, 2), default=0)  # AC
    
    # 偏差指标
    cost_variance = Column(Numeric(15, 2), default=0)  # CV = EV - AC
    schedule_variance = Column(Numeric(15, 2), default=0)  # SV = EV - PV
    
    # 绩效指标
    cost_performance_index = Column(Numeric(5, 4), default=1.0)  # CPI = EV / AC
    schedule_performance_index = Column(Numeric(5, 4), default=1.0)  # SPI = EV / PV
    
    # 预测指标
    estimate_at_completion = Column(Numeric(15, 2), default=0)  # EAC
    estimate_to_complete = Column(Numeric(15, 2), default=0)  # ETC = EAC - AC
    variance_at_completion = Column(Numeric(15, 2), default=0)  # VAC = BAC - EAC
    to_complete_performance_index = Column(Numeric(5, 4), default=1.0)  # TCPI
    
    # AI分析
    ai_predictions = Column(JSON)  # AI预测结果
    
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    
    # 关系
    project = relationship("Project", back_populates="evm_snapshots")
    
    __table_args__ = (
        Index("ix_evm_project_date", "project_id", "snapshot_date"),
    )
    
    def __repr__(self):
        return f"<EVMSnapshot {self.project_id} @ {self.snapshot_date}>"


class Milestone(Base):
    """里程碑模型"""
    __tablename__ = "milestones"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True)  # 关联任务
    
    name = Column(String(255), nullable=False)
    description = Column(Text)
    due_date = Column(Date)
    
    status = Column(String(20), default="pending")  # pending/completed/delayed
    completed_at = Column(DateTime(timezone=True))
    
    # 阶段门配置
    gate_criteria = Column(JSON, default=list)  # 通过标准
    approved_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    
    # 关系
    project = relationship("Project", back_populates="milestones")
    task = relationship("Task")
    approver = relationship("User")
    
    def __repr__(self):
        return f"<Milestone {self.name}>"


from app.models.comment import Comment
from app.models.notification import Notification
from app.models.attachment import Attachment
from app.models.message import Message, Channel, ChannelMember, MessageReaction
from app.models.integration import Integration
from app.models.sprint import Sprint, SprintTask
from app.models.epic import Epic, EpicTask
from app.models.release import Release, ReleaseTask
from app.models.task_template import TaskTemplate
from app.models.recurring_task import RecurringTask, RecurringTaskInstance
from app.models.wiki import WikiSpace, WikiPage, WikiPageVersion, WikiComment
from app.models.risk import RiskAlert
from app.models.compliance import (
    CompliancePolicy, ComplianceControl, ComplianceAudit, ComplianceEvidence
)
from app.models.budget import ProjectBudget, BudgetCategory, CostRecord
from app.models.app_market import AppPlugin, AppInstallation
from app.models.llm_config import LLMConfig
from app.models.system_llm_config import SystemLLMConfig
from app.models.api_key import ApiKey
from app.models.ai_agent import AgentSession
from app.models.scheduled_task import ScheduledJob, JobExecutionLog
from app.models.form import FormTemplate, FormSubmission
from app.models.automation import AutomationRule
from app.models.custom_field import CustomField, CustomFieldValue
from app.models.webhook import Webhook, WebhookDelivery
from app.models.permission import Role, ProjectMember
from app.models.knowledge_base import KnowledgeBase, KnowledgeDocument, KnowledgeChunk, KnowledgeBaseShare, UserGroup, UserGroupMember, ShareType, SharePermission
from app.models.okr_whiteboard_document import Objective, Whiteboard, Document
from app.models.pm_extras import Lesson, ChangeRequest
from app.models.zapier import ZapierSubscription
from app.models.openclaw_config import OpenClawConfig
from app.models.llm_call_log import LLMCallLog
from app.models.async_task import AsyncTask, AsyncTaskStatus
from app.models.ucm import (
    Organization, Department, UserOrganization,
    Feature, Plan, PlanFeature, UserFeatureGrant,
    Order, OrderItem, Refund, Transaction,
    UserLevel, UserLevelRecord,
)


class AuditLog(Base):
    """审计日志模型"""
    __tablename__ = "audit_logs"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    action = Column(String(50), nullable=False)  # create/update/delete
    entity_type = Column(String(50), nullable=False)  # project/task/risk
    entity_id = Column(String(36), nullable=False)
    
    changes = Column(JSON)  # 变更内容
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    
    # 关系
    user = relationship("User")
    
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_user", "user_id"),
        Index("ix_audit_time", "created_at"),
    )
    
    def __repr__(self):
        return f"<AuditLog {self.action} {self.entity_type}@{self.entity_id[:8]}>"

from app.models.im_gateway import IMProviderConfig, UserIMBinding, IMConversationSession, IMAuditLog
from app.models.project_type import ProjectType

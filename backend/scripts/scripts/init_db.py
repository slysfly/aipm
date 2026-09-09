"""
PMI中国AI项目管理社区 - 数据库初始化脚本
创建所有表并插入初始数据
用法:
    python scripts/init_db.py           # 创建表（如果不存在）
    python scripts/init_db.py --reset   # 删除并重新创建所有表
"""

import asyncio
import argparse
import sys
import os
import logging
import secrets
from datetime import datetime, date, timedelta
from decimal import Decimal

# 将backend目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import Base, engine, async_session_maker
from app.config import settings

# 导入所有模型，确保它们注册到 Base.metadata
from app.models import (
    User, Project, Task, TaskDependency, Portfolio, Resource, ResourceAllocation,
    Risk, EVMSnapshot, Milestone, Comment, Notification, Attachment, AuditLog,
    Message, Channel, ChannelMember, MessageReaction,
    Integration, Sprint, SprintTask, Epic, EpicTask, Release, ReleaseTask,
    TaskTemplate, RecurringTask, RecurringTaskInstance,
    WikiSpace, WikiPage, WikiPageVersion, WikiComment,
    RiskAlert, CompliancePolicy, ComplianceControl, ComplianceAudit, ComplianceEvidence,
    ProjectBudget, BudgetCategory, CostRecord,
    AppPlugin, AppInstallation, LLMConfig, AgentSession,
    ScheduledJob, JobExecutionLog, FormTemplate, FormSubmission,
    ApprovalFlow, ApprovalInstance, ApprovalStep, ApprovalDelegate,
    AutomationRule, CustomField, CustomFieldValue,
    Webhook, WebhookDelivery, Role, ProjectMember,
)

from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

_STRONG_PASSWORD_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _generate_strong_password(length: int = 16) -> str:
    """生成包含大小写字母与数字的随机强密码。"""
    return "".join(secrets.choice(_STRONG_PASSWORD_ALPHABET) for _ in range(length))


def _resolve_initial_admin_password() -> str:
    """返回用于初始化演示管理员的明文口令。

    优先读取配置项 INITIAL_ADMIN_PASSWORD；若该值为空（生产环境未设置强密码），
    则生成一个随机强密码并记录到日志，避免任何明文弱口令残留。
    """
    raw: str = getattr(settings, "INITIAL_ADMIN_PASSWORD", "") or ""
    if not raw:
        raw = _generate_strong_password(16)
        logger.warning(
            "INITIAL_ADMIN_PASSWORD 为空，已为演示管理员生成随机强密码: %s",
            raw,
        )
    return raw


async def drop_all_tables():
    """删除所有表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("所有表已删除")


async def create_all_tables():
    """创建所有表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("所有表已创建")


async def init_data():
    """插入初始数据"""
    async with async_session_maker() as session:
        # 检查是否已有数据
        result = await session.execute(text("SELECT COUNT(*) FROM users"))
        count = result.scalar()
        if count and count > 0:
            print("数据库已有数据，跳过初始化")
            return

        now = datetime.utcnow()
        today = date.today()

        # 1. 创建管理员用户
        admin_user = User(
            id="admin-0000-0000-0000-000000000001",
            email="admin@tongwei.com",
            username="admin",
            hashed_password=get_password_hash(_resolve_initial_admin_password()),
            full_name="系统管理员",
            phone="13800000001",
            department="信息技术部",
            position="系统管理员",
            is_active=True,
            is_superuser=True,
            last_login=now,
        )
        session.add(admin_user)

        # 2. 创建示例项目
        demo_project = Project(
            id="proj-0000-0000-0000-000000000001",
            name="PMI中国AI项目管理社区",
            description="企业级AI驱动的项目管理系统，支持敏捷、瀑布、混合方法论",
            industry_type="it_software",
            project_type="agile",
            status="active",
            priority=1,
            color="#1890ff",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=90),
            baseline_start=today - timedelta(days=30),
            baseline_end=today + timedelta(days=90),
            budget=Decimal("500000.00"),
            baseline_budget=Decimal("500000.00"),
            actual_cost=Decimal("120000.00"),
            owner_id=admin_user.id,
            settings={"sprint_length": 14, "story_points_scale": [1, 2, 3, 5, 8, 13]},
        )
        session.add(demo_project)

        # 3. 创建示例任务
        tasks_data = [
            {
                "id": "task-0000-0000-0000-000000000001",
                "name": "系统架构设计",
                "description": "设计整体系统架构，包括前端、后端、数据库和AI模块",
                "wbs_code": "1.1",
                "level": 0,
                "estimated_hours": Decimal("80"),
                "actual_hours": Decimal("75"),
                "status": "done",
                "priority": 1,
                "progress": Decimal("100"),
                "assignee_id": admin_user.id,
                "is_milestone": False,
                "category": "设计",
            },
            {
                "id": "task-0000-0000-0000-000000000002",
                "name": "数据库模型设计",
                "description": "设计ER图，创建所有数据模型和关系",
                "wbs_code": "1.2",
                "level": 0,
                "estimated_hours": Decimal("40"),
                "actual_hours": Decimal("42"),
                "status": "done",
                "priority": 1,
                "progress": Decimal("100"),
                "assignee_id": admin_user.id,
                "is_milestone": False,
                "category": "设计",
            },
            {
                "id": "task-0000-0000-0000-000000000003",
                "name": "用户认证模块",
                "description": "实现JWT认证、用户注册、登录、密码重置功能",
                "wbs_code": "2.1",
                "level": 0,
                "estimated_hours": Decimal("60"),
                "actual_hours": Decimal("55"),
                "status": "done",
                "priority": 1,
                "progress": Decimal("100"),
                "assignee_id": admin_user.id,
                "is_milestone": False,
                "category": "开发",
            },
            {
                "id": "task-0000-0000-0000-000000000004",
                "name": "项目管理核心功能",
                "description": "实现项目CRUD、任务管理、看板、甘特图",
                "wbs_code": "2.2",
                "level": 0,
                "estimated_hours": Decimal("120"),
                "actual_hours": Decimal("80"),
                "status": "in_progress",
                "priority": 1,
                "progress": Decimal("65"),
                "assignee_id": admin_user.id,
                "is_milestone": False,
                "category": "开发",
            },
            {
                "id": "task-0000-0000-0000-000000000005",
                "name": "AI智能助手集成",
                "description": "集成LLM，实现任务分解、风险预测、智能报告",
                "wbs_code": "2.3",
                "level": 0,
                "estimated_hours": Decimal("100"),
                "actual_hours": Decimal("20"),
                "status": "in_progress",
                "priority": 2,
                "progress": Decimal("20"),
                "assignee_id": admin_user.id,
                "is_milestone": False,
                "category": "开发",
            },
            {
                "id": "task-0000-0000-0000-000000000006",
                "name": "MVP版本发布",
                "description": "完成MVP版本开发并发布",
                "wbs_code": "3.1",
                "level": 0,
                "estimated_hours": Decimal("40"),
                "actual_hours": Decimal("0"),
                "status": "todo",
                "priority": 1,
                "progress": Decimal("0"),
                "assignee_id": admin_user.id,
                "is_milestone": True,
                "category": "发布",
            },
        ]

        for t_data in tasks_data:
            task = Task(
                id=t_data["id"],
                project_id=demo_project.id,
                name=t_data["name"],
                description=t_data["description"],
                wbs_code=t_data["wbs_code"],
                level=t_data["level"],
                estimated_hours=t_data["estimated_hours"],
                actual_hours=t_data["actual_hours"],
                status=t_data["status"],
                priority=t_data["priority"],
                progress=t_data["progress"],
                assignee_id=t_data["assignee_id"],
                is_milestone=t_data["is_milestone"],
                category=t_data["category"],
                planned_start=now - timedelta(days=20),
                planned_end=now + timedelta(days=10),
            )
            session.add(task)

        # 4. 创建里程碑
        milestone = Milestone(
            id="ms-0000-0000-0000-000000000001",
            project_id=demo_project.id,
            name="MVP版本发布",
            description="完成核心功能开发并发布MVP版本",
            due_date=today + timedelta(days=30),
            status="pending",
            sort_order=1,
        )
        session.add(milestone)

        # 5. 创建角色
        admin_role = Role(
            id="role-0000-0000-0000-000000000001",
            name="管理员",
            description="系统管理员，拥有所有权限",
            permissions=[p.value for p in [
                # 从 permission.py 导入的 Permission 枚举
            ]],
            is_system=True,
        )
        # 手动添加所有权限
        from app.models.permission import Permission
        admin_role.permissions = [p.value for p in Permission]
        session.add(admin_role)

        member_role = Role(
            id="role-0000-0000-0000-000000000002",
            name="成员",
            description="普通项目成员",
            permissions=[
                "project.view", "task.view", "task.create", "task.edit",
                "comment.view", "comment.create", "file.view", "file.upload",
            ],
            is_system=True,
        )
        session.add(member_role)

        # 6. 创建项目成员关系
        project_member = ProjectMember(
            id="pm-0000-0000-0000-000000000001",
            project_id=demo_project.id,
            user_id=admin_user.id,
            role_id=admin_role.id,
            is_active=True,
        )
        session.add(project_member)

        # 7. 创建示例审批流程
        approval_flow = ApprovalFlow(
            id="flow-0000-0000-0000-000000000001",
            name="预算审批流程",
            description="项目预算变更审批流程",
            entity_type="budget",
            steps=[
                {"step_order": 1, "approver_role": "项目经理", "approver_id": admin_user.id, "condition": None},
                {"step_order": 2, "approver_role": "财务总监", "approver_id": admin_user.id, "condition": None},
            ],
            is_active=True,
            created_by=admin_user.id,
        )
        session.add(approval_flow)

        # 8. 创建Wiki空间
        wiki_space = WikiSpace(
            id="wiki-0000-0000-0000-000000000001",
            name="项目文档",
            description="PMI中国AI项目管理社区的知识库",
            icon="book",
            color="#1890ff",
            is_public=True,
            owner_id=admin_user.id,
        )
        session.add(wiki_space)

        wiki_page = WikiPage(
            id="wp-0000-0000-0000-000000000001",
            space_id=wiki_space.id,
            title="项目简介",
            content="# PMI中国AI项目管理社区\n\n企业级AI驱动的项目管理系统...",
            created_by=admin_user.id,
            version=1,
        )
        session.add(wiki_page)

        # 9. 创建预算
        project_budget = ProjectBudget(
            id="budget-0000-0000-0000-000000000001",
            project_id=demo_project.id,
            total_budget=Decimal("500000.00"),
            currency="CNY",
            labor_rate=Decimal("500.00"),
            overhead_rate=Decimal("0.1500"),
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=90),
            status="active",
            created_by=admin_user.id,
        )
        session.add(project_budget)

        budget_category = BudgetCategory(
            id="bc-0000-0000-0000-000000000001",
            budget_id=project_budget.id,
            name="人力成本",
            allocated_amount=Decimal("300000.00"),
            spent_amount=Decimal("80000.00"),
            description="开发人员、测试人员、产品经理人力成本",
        )
        session.add(budget_category)

        cost_record = CostRecord(
            id="cost-0000-0000-0000-000000000001",
            project_id=demo_project.id,
            budget_id=project_budget.id,
            category_id=budget_category.id,
            cost_type="labor",
            amount=Decimal("5000.00"),
            description="3月第一周人力成本",
            recorded_by=admin_user.id,
            work_hours=Decimal("40.00"),
            labor_rate_at_record=Decimal("500.00"),
        )
        session.add(cost_record)

        await session.commit()
        print("初始数据已插入")


async def main():
    parser = argparse.ArgumentParser(description="数据库初始化脚本")
    parser.add_argument("--reset", action="store_true", help="删除并重新创建所有表")
    args = parser.parse_args()

    if args.reset:
        await drop_all_tables()

    await create_all_tables()
    await init_data()
    print("数据库初始化完成！")


if __name__ == "__main__":
    asyncio.run(main())

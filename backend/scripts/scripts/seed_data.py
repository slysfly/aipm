"""
PMI中国AI项目管理社区 - 种子数据脚本
插入丰富的示例数据用于开发和演示
用法:
    python scripts/seed_data.py         # 插入种子数据
    python scripts/seed_data.py --reset # 清空并重新插入
"""

import asyncio
import argparse
import sys
import os
import random
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import async_session_maker, engine
from app.core.security import get_password_hash

from app.models import (
    User, Project, Task, Portfolio, Resource, Risk, Milestone,
    Sprint, SprintTask, Epic, EpicTask, Release, ReleaseTask,
    WikiSpace, WikiPage, WikiPageVersion, WikiComment,
    ProjectBudget, BudgetCategory, CostRecord,
    ApprovalFlow, ApprovalInstance, ApprovalStep,
    Role, ProjectMember, Comment, Notification,
)


# 随机数据生成辅助函数
def random_date(start, end):
    """生成随机日期"""
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))


def random_datetime(start, end):
    """生成随机时间"""
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


# 种子数据配置
PROJECT_NAMES = [
    "智能客服系统升级",
    "企业数据中台建设",
    "移动端APP重构",
    "AI预测分析平台",
    "供应链管理系统",
]

USER_DATA = [
    {"username": "zhangsan", "full_name": "张三", "email": "zhangsan@tongwei.com", "dept": "研发部", "pos": "高级工程师"},
    {"username": "lisi", "full_name": "李四", "email": "lisi@tongwei.com", "dept": "产品部", "pos": "产品经理"},
    {"username": "wangwu", "full_name": "王五", "email": "wangwu@tongwei.com", "dept": "测试部", "pos": "测试工程师"},
    {"username": "zhaoliu", "full_name": "赵六", "email": "zhaoliu@tongwei.com", "dept": "运维部", "pos": "运维工程师"},
    {"username": "sunqi", "full_name": "孙七", "email": "sunqi@tongwei.com", "dept": "设计部", "pos": "UI设计师"},
]

TASK_TEMPLATES = [
    "需求分析", "技术方案设计", "数据库设计", "接口开发", "前端页面开发",
    "单元测试", "集成测试", "代码审查", "Bug修复", "性能优化",
    "文档编写", "用户培训", "数据迁移", "部署上线", "监控配置",
]

WIKI_TITLES = [
    "项目概述", "技术架构", "开发规范", "API文档", "部署手册",
    "用户指南", "常见问题", "版本历史", "团队成员", "会议记录",
]


async def clear_data(session):
    """清空所有数据（保留表结构）"""
    tables = [
        "wiki_comments", "wiki_page_versions", "wiki_pages", "wiki_spaces",
        "cost_records", "budget_categories", "project_budgets",
        "approval_steps", "approval_instances", "approval_flows", "approval_delegates",
        "recurring_task_instances", "recurring_tasks",
        "release_tasks", "releases",
        "epic_tasks", "epics",
        "sprint_tasks", "sprints",
        "task_dependencies", "task_templates",
        "resource_allocations", "resources",
        "evm_snapshots", "milestones", "risks", "risk_alerts",
        "comments", "attachments", "notifications", "audit_logs",
        "project_members", "roles",
        "tasks", "projects", "portfolios", "users",
    ]
    for table in tables:
        try:
            await session.execute(f"DELETE FROM {table}")
        except Exception:
            pass
    await session.commit()
    print("所有数据已清空")


async def seed_users(session):
    """创建5个用户"""
    users = []
    for i, u in enumerate(USER_DATA):
        user = User(
            id=f"user-{i+1:04d}-0000-0000-000000000000",
            email=u["email"],
            username=u["username"],
            hashed_password=get_password_hash("password123"),
            full_name=u["full_name"],
            phone=f"138{i+2:08d}",
            department=u["dept"],
            position=u["pos"],
            is_active=True,
            is_superuser=False,
        )
        session.add(user)
        users.append(user)
    await session.flush()
    print(f"已创建 {len(users)} 个用户")
    return users


async def seed_roles(session):
    """创建角色"""
    roles = []
    role_data = [
        {"name": "项目经理", "perms": ["project.view", "project.edit", "task.view", "task.create", "task.edit", "task.assign", "member.invite"]},
        {"name": "开发人员", "perms": ["project.view", "task.view", "task.create", "task.edit", "comment.view", "comment.create", "file.view", "file.upload"]},
        {"name": "测试人员", "perms": ["project.view", "task.view", "task.edit", "comment.view", "comment.create"]},
        {"name": "产品经理", "perms": ["project.view", "project.edit", "task.view", "task.create", "task.edit", "settings.view"]},
    ]
    for i, r in enumerate(role_data):
        role = Role(
            id=f"role-{i+1:04d}-0000-0000-000000000000",
            name=r["name"],
            permissions=r["perms"],
            is_system=False,
        )
        session.add(role)
        roles.append(role)
    await session.flush()
    print(f"已创建 {len(roles)} 个角色")
    return roles


async def seed_projects(session, users):
    """创建5个项目（不同状态）"""
    projects = []
    statuses = ["planning", "active", "active", "paused", "completed"]
    priorities = [1, 2, 3, 2, 1]
    budgets = [Decimal("800000"), Decimal("1200000"), Decimal("600000"), Decimal("450000"), Decimal("1000000")]
    colors = ["#1890ff", "#52c41a", "#faad14", "#f5222d", "#722ed1"]

    for i, name in enumerate(PROJECT_NAMES):
        start = date.today() - timedelta(days=random.randint(10, 60))
        end = start + timedelta(days=random.randint(90, 180))
        owner = random.choice(users)

        project = Project(
            id=f"proj-{i+1:04d}-0000-0000-000000000000",
            name=name,
            description=f"{name}项目，旨在提升企业数字化能力和运营效率",
            industry_type=random.choice(["it_software", "finance", "manufacturing", "healthcare", "consulting"]),
            project_type=random.choice(["agile", "waterfall", "hybrid", "kanban"]),
            status=statuses[i],
            priority=priorities[i],
            color=colors[i],
            start_date=start,
            end_date=end,
            baseline_start=start,
            baseline_end=end,
            budget=budgets[i],
            baseline_budget=budgets[i],
            actual_cost=budgets[i] * Decimal(str(random.uniform(0.2, 0.8))),
            owner_id=owner.id,
            settings={"sprint_length": 14, "story_points_scale": [1, 2, 3, 5, 8, 13]},
        )
        session.add(project)
        projects.append(project)
    await session.flush()
    print(f"已创建 {len(projects)} 个项目")
    return projects


async def seed_project_members(session, projects, users, roles):
    """为每个项目分配成员"""
    count = 0
    for project in projects:
        for user in users:
            if random.random() > 0.3:  # 70%概率加入项目
                pm = ProjectMember(
                    id=f"pm-{count:06d}-0000-0000-000000000000",
                    project_id=project.id,
                    user_id=user.id,
                    role_id=random.choice(roles).id,
                    is_active=True,
                )
                session.add(pm)
                count += 1
    await session.flush()
    print(f"已创建 {count} 个项目成员关系")


async def seed_tasks(session, projects, users):
    """为每个项目创建10-20个任务"""
    tasks = []
    task_statuses = ["backlog", "todo", "in_progress", "in_review", "testing", "done", "cancelled"]
    task_priorities = [1, 2, 3, 4, 5]
    categories = ["需求", "设计", "开发", "测试", "运维", "文档"]

    for project in projects:
        num_tasks = random.randint(10, 20)
        for j in range(num_tasks):
            template = random.choice(TASK_TEMPLATES)
            status = random.choice(task_statuses)
            progress = {
                "backlog": 0, "todo": 0, "in_progress": random.randint(10, 80),
                "in_review": 90, "testing": 95, "done": 100, "cancelled": 0
            }[status]

            est_hours = Decimal(str(random.randint(4, 80)))
            actual = est_hours * Decimal(str(random.uniform(0.3, 1.2))) if status in ["in_progress", "in_review", "testing", "done"] else Decimal("0")

            task = Task(
                id=f"task-{len(tasks)+1:06d}-0000-0000-000000000000",
                project_id=project.id,
                name=f"{project.name} - {template} {j+1}",
                description=f"{template}任务的详细描述，属于{project.name}项目",
                wbs_code=f"{project.id}.{j+1}",
                level=0,
                estimated_hours=est_hours,
                actual_hours=round(actual, 2),
                status=status,
                priority=random.choice(task_priorities),
                progress=Decimal(str(progress)),
                assignee_id=random.choice(users).id if random.random() > 0.2 else None,
                is_milestone=(j == num_tasks - 1),
                category=random.choice(categories),
                planned_start=datetime.utcnow() - timedelta(days=random.randint(0, 30)),
                planned_end=datetime.utcnow() + timedelta(days=random.randint(7, 60)),
                labels=[random.choice(["urgent", "frontend", "backend", "ai", "database"])] if random.random() > 0.5 else [],
            )
            session.add(task)
            tasks.append(task)
    await session.flush()
    print(f"已创建 {len(tasks)} 个任务")
    return tasks


async def seed_sprints(session, projects):
    """为活跃项目创建Sprint"""
    sprints = []
    statuses = ["planning", "active", "completed", "closed"]

    for i, project in enumerate(projects):
        if project.status != "active":
            continue
        for j in range(3):
            start = date.today() - timedelta(days=30) + timedelta(days=j*14)
            end = start + timedelta(days=13)
            sprint = Sprint(
                id=f"sprint-{len(sprints)+1:04d}-0000-0000-000000000000",
                name=f"Sprint {j+1}",
                goal=f"完成{project.name}第{j+1}阶段目标",
                start_date=start,
                end_date=end,
                status=statuses[j] if j < len(statuses) else "planning",
                project_id=project.id,
                velocity=random.randint(20, 60),
                capacity=random.randint(40, 80),
                created_by=project.owner_id,
            )
            session.add(sprint)
            sprints.append(sprint)
    await session.flush()
    print(f"已创建 {len(sprints)} 个Sprint")
    return sprints


async def seed_epics(session, projects):
    """为每个项目创建Epic"""
    epics = []
    for project in projects:
        for j in range(random.randint(2, 4)):
            epic = Epic(
                id=f"epic-{len(epics)+1:04d}-0000-0000-000000000000",
                name=f"{project.name} 功能模块 {j+1}",
                description=f"{project.name}的核心功能模块{j+1}，包含多个用户故事",
                color=random.choice(["#1890ff", "#52c41a", "#faad14", "#f5222d", "#722ed1"]),
                status=random.choice(["backlog", "in_progress", "done"]),
                project_id=project.id,
                start_date=date.today() - timedelta(days=random.randint(0, 20)),
                end_date=date.today() + timedelta(days=random.randint(30, 90)),
                progress=Decimal(str(random.randint(0, 100))),
                story_points_total=random.randint(20, 100),
                story_points_completed=random.randint(0, 50),
                created_by=project.owner_id,
            )
            session.add(epic)
            epics.append(epic)
    await session.flush()
    print(f"已创建 {len(epics)} 个Epic")
    return epics


async def seed_releases(session, projects):
    """为每个项目创建版本"""
    releases = []
    for project in projects:
        for j in range(random.randint(1, 3)):
            release = Release(
                id=f"rel-{len(releases)+1:04d}-0000-0000-000000000000",
                name=f"v{j+1}.0",
                version=f"{j+1}.0.0",
                description=f"{project.name}第{j+1}个主要版本",
                status=random.choice(["planning", "released", "archived"]),
                project_id=project.id,
                release_date=date.today() + timedelta(days=random.randint(-30, 60)),
                created_by=project.owner_id,
            )
            session.add(release)
            releases.append(release)
    await session.flush()
    print(f"已创建 {len(releases)} 个版本")
    return releases


async def seed_budgets(session, projects, users):
    """为每个项目创建预算和成本记录"""
    budgets = []
    cost_types = ["labor", "material", "overhead", "travel", "other"]

    for project in projects:
        budget = ProjectBudget(
            id=f"budget-{len(budgets)+1:04d}-0000-0000-000000000000",
            project_id=project.id,
            total_budget=project.budget,
            currency="CNY",
            labor_rate=Decimal(str(random.randint(300, 800))),
            overhead_rate=Decimal(str(random.uniform(0.1, 0.25))),
            start_date=project.start_date,
            end_date=project.end_date,
            status=random.choice(["draft", "active", "exceeded", "closed"]),
            created_by=project.owner_id,
        )
        session.add(budget)
        budgets.append(budget)

        # 创建预算分类
        categories = [
            {"name": "人力成本", "alloc": project.budget * Decimal("0.6")},
            {"name": "硬件设备", "alloc": project.budget * Decimal("0.15")},
            {"name": "软件许可", "alloc": project.budget * Decimal("0.1")},
            {"name": "外包服务", "alloc": project.budget * Decimal("0.1")},
            {"name": "其他费用", "alloc": project.budget * Decimal("0.05")},
        ]

        cats = []
        for c in categories:
            cat = BudgetCategory(
                id=f"bc-{len(budgets)}-{len(cats)+1:03d}-0000-000000000000",
                budget_id=budget.id,
                name=c["name"],
                allocated_amount=c["alloc"],
                spent_amount=c["alloc"] * Decimal(str(random.uniform(0.1, 0.9))),
                description=f"{c['name']}预算分类",
            )
            session.add(cat)
            cats.append(cat)
        await session.flush()

        # 创建成本记录
        for _ in range(random.randint(3, 8)):
            cat = random.choice(cats)
            cost = CostRecord(
                id=f"cost-{uuid.uuid4().hex[:8]}-0000-000000000000",
                project_id=project.id,
                budget_id=budget.id,
                category_id=cat.id,
                cost_type=random.choice(cost_types),
                amount=Decimal(str(random.randint(1000, 50000))),
                description=f"{cat.name}相关支出",
                recorded_by=random.choice(users).id,
                work_hours=Decimal(str(random.randint(8, 160))) if random.random() > 0.5 else Decimal("0"),
            )
            session.add(cost)

    await session.flush()
    print(f"已创建 {len(budgets)} 个项目预算及相关成本记录")
    return budgets


async def seed_wiki(session, projects, users):
    """创建Wiki空间和页面"""
    spaces = []
    for project in projects:
        space = WikiSpace(
            id=f"wiki-{len(spaces)+1:04d}-0000-0000-000000000000",
            name=f"{project.name} 知识库",
            description=f"{project.name}项目的知识管理和文档中心",
            icon=random.choice(["book", "file-text", "folder", "globe", "database"]),
            color=project.color,
            is_public=random.choice([True, False]),
            owner_id=project.owner_id,
        )
        session.add(space)
        spaces.append(space)
    await session.flush()

    pages = []
    for space in spaces:
        for title in random.sample(WIKI_TITLES, k=random.randint(3, 6)):
            page = WikiPage(
                id=f"wp-{len(pages)+1:06d}-0000-0000-000000000000",
                space_id=space.id,
                title=title,
                content=f"# {title}\n\n这是{space.name}的{title}文档内容。\n\n## 概述\n\n详细内容待补充...",
                created_by=space.owner_id,
                version=1,
            )
            session.add(page)
            pages.append(page)
    await session.flush()
    print(f"已创建 {len(spaces)} 个Wiki空间和 {len(pages)} 个页面")
    return spaces, pages


async def seed_approvals(session, projects, users):
    """创建审批流程和实例"""
    flows = []
    flow_data = [
        {"name": "预算变更审批", "entity": "budget"},
        {"name": "任务延期审批", "entity": "task"},
        {"name": "费用报销审批", "entity": "expense"},
    ]

    for fd in flow_data:
        flow = ApprovalFlow(
            id=f"flow-{len(flows)+1:04d}-0000-0000-000000000000",
            name=fd["name"],
            description=f"{fd['name']}流程定义",
            entity_type=fd["entity"],
            steps=[
                {"step_order": 1, "approver_role": "直属领导", "approver_id": random.choice(users).id},
                {"step_order": 2, "approver_role": "部门总监", "approver_id": random.choice(users).id},
            ],
            is_active=True,
            created_by=random.choice(users).id,
        )
        session.add(flow)
        flows.append(flow)
    await session.flush()

    # 创建审批实例
    instances = []
    for _ in range(5):
        flow = random.choice(flows)
        instance = ApprovalInstance(
            id=f"ai-{len(instances)+1:04d}-0000-0000-000000000000",
            flow_id=flow.id,
            entity_type=flow.entity_type,
            entity_id=random.choice(projects).id,
            requester_id=random.choice(users).id,
            status=random.choice(["pending", "approved", "rejected"]),
            current_step=random.randint(0, 1),
        )
        session.add(instance)
        instances.append(instance)
    await session.flush()

    # 创建审批步骤
    for inst in instances:
        for step_order in range(1, 3):
            step = ApprovalStep(
                id=f"step-{inst.id}-{step_order}",
                instance_id=inst.id,
                step_order=step_order,
                approver_id=random.choice(users).id,
                status=random.choice(["pending", "approved", "rejected"]),
                comment=random.choice([None, "同意", "需要修改", "通过"]),
            )
            session.add(step)

    await session.flush()
    print(f"已创建 {len(flows)} 个审批流程和 {len(instances)} 个审批实例")
    return flows


async def seed_milestones(session, projects):
    """为每个项目创建里程碑"""
    milestones = []
    milestone_names = ["需求冻结", "设计评审", "开发完成", "测试通过", "正式上线"]

    for project in projects:
        for j, name in enumerate(milestone_names):
            ms = Milestone(
                id=f"ms-{len(milestones)+1:06d}-0000-000000000000",
                project_id=project.id,
                name=name,
                description=f"{project.name}的{name}里程碑",
                due_date=project.start_date + timedelta(days=(j+1)*30),
                status=random.choice(["pending", "completed", "delayed"]),
                sort_order=j,
            )
            session.add(ms)
            milestones.append(ms)
    await session.flush()
    print(f"已创建 {len(milestones)} 个里程碑")
    return milestones


async def seed_risks(session, projects, users):
    """为每个项目创建风险记录"""
    risks = []
    risk_names = [
        "技术选型风险", "人员流失风险", "需求变更风险", "进度延期风险",
        "预算超支风险", "第三方依赖风险", "性能瓶颈风险", "安全漏洞风险",
    ]

    for project in projects:
        for _ in range(random.randint(2, 4)):
            prob = Decimal(str(random.uniform(0.1, 0.9)))
            impact = Decimal(str(random.uniform(0.1, 0.9)))
            risk = Risk(
                id=f"risk-{len(risks)+1:06d}-0000-000000000000",
                project_id=project.id,
                name=random.choice(risk_names),
                description="潜在风险描述，需要持续监控和应对",
                category=random.choice(["technical", "schedule", "cost", "resource", "quality", "external", "business"]),
                probability=prob,
                impact=impact,
                risk_score=round(prob * impact, 4),
                status=random.choice(["identified", "analyzing", "mitigating", "occurred", "closed"]),
                owner_id=random.choice(users).id,
                response_strategy=random.choice(["avoid", "mitigate", "transfer", "accept"]),
            )
            session.add(risk)
            risks.append(risk)
    await session.flush()
    print(f"已创建 {len(risks)} 个风险记录")
    return risks


async def seed_comments_and_notifications(session, tasks, users):
    """创建评论和通知"""
    comments = []
    for task in tasks[:20]:  # 只为前20个任务添加评论
        for _ in range(random.randint(0, 3)):
            comment = Comment(
                id=f"cm-{len(comments)+1:06d}-0000-000000000000",
                task_id=task.id,
                project_id=task.project_id,
                user_id=random.choice(users).id,
                content=random.choice([
                    "这个任务进度正常",
                    "需要更多资源支持",
                    "遇到技术难点，需要讨论",
                    "已完成初步方案",
                    "等待第三方接口",
                ]),
            )
            session.add(comment)
            comments.append(comment)

    notifications = []
    for user in users:
        for _ in range(random.randint(2, 5)):
            notif = Notification(
                id=f"notif-{len(notifications)+1:06d}-0000-000000000000",
                user_id=user.id,
                type=random.choice(["task_assigned", "task_due", "mention", "project_update"]),
                title=random.choice(["任务分配", "即将到期", "有人@你", "项目更新"]),
                content="这是一条示例通知内容",
                related_type="task",
                related_id=random.choice(tasks).id if tasks else None,
                is_read=random.choice([True, False]),
            )
            session.add(notif)
            notifications.append(notif)

    await session.flush()
    print(f"已创建 {len(comments)} 条评论和 {len(notifications)} 条通知")


async def main():
    parser = argparse.ArgumentParser(description="种子数据脚本")
    parser.add_argument("--reset", action="store_true", help="清空现有数据后重新插入")
    args = parser.parse_args()

    async with async_session_maker() as session:
        if args.reset:
            await clear_data(session)

        print("=" * 50)
        print("开始插入种子数据...")
        print("=" * 50)

        users = await seed_users(session)
        roles = await seed_roles(session)
        projects = await seed_projects(session, users)
        await seed_project_members(session, projects, users, roles)
        tasks = await seed_tasks(session, projects, users)
        await seed_sprints(session, projects)
        await seed_epics(session, projects)
        await seed_releases(session, projects)
        await seed_budgets(session, projects, users)
        await seed_wiki(session, projects, users)
        await seed_approvals(session, projects, users)
        await seed_milestones(session, projects)
        await seed_risks(session, projects, users)
        await seed_comments_and_notifications(session, tasks, users)

        await session.commit()
        print("=" * 50)
        print("种子数据插入完成！")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())

"""
PMI中国AI项目管理社区 - NLP查询引擎辅助模块
包含实体映射、字段映射、序列化等工具函数
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import joinedload

from app.models import User, Project, Task, TaskStatus, TaskPriority, Risk, Milestone, Comment

import enum


# 实体映射：自然语言实体名 -> SQLAlchemy模型
ENTITY_MAP = {
    "task": Task,
    "任务": Task,
    "tasks": Task,
    "project": Project,
    "项目": Project,
    "projects": Project,
    "user": User,
    "用户": User,
    "users": User,
    "member": User,
    "成员": User,
    "risk": Risk,
    "风险": Risk,
    "risks": Risk,
    "milestone": Milestone,
    "里程碑": Milestone,
    "milestones": Milestone,
    "comment": Comment,
    "评论": Comment,
    "comments": Comment,
}

# 字段映射：常见自然语言字段名 -> 数据库字段名
FIELD_MAP = {
    # Task字段
    "status": "status",
    "状态": "status",
    "priority": "priority",
    "优先级": "priority",
    "assignee": "assignee_id",
    "负责人": "assignee_id",
    "执行人": "assignee_id",
    "指派给": "assignee_id",
    "due_date": "planned_end",
    "截止日期": "planned_end",
    "截止时间": "planned_end",
    "完成时间": "actual_end",
    "completed_at": "actual_end",
    "created_at": "created_at",
    "创建时间": "created_at",
    "updated_at": "updated_at",
    "更新时间": "updated_at",
    "progress": "progress",
    "进度": "progress",
    "name": "name",
    "名称": "name",
    "title": "name",
    "project_id": "project_id",
    "项目id": "project_id",
    # Project字段
    "owner": "owner_id",
    "所有者": "owner_id",
    "start_date": "start_date",
    "开始日期": "start_date",
    "end_date": "end_date",
    "结束日期": "end_date",
    "budget": "budget",
    "预算": "budget",
    # User字段
    "username": "username",
    "用户名": "username",
    "email": "email",
    "邮箱": "email",
    "department": "department",
    "部门": "department",
    "position": "position",
    "职位": "position",
    "full_name": "full_name",
    "姓名": "full_name",
    # Risk字段
    "category": "category",
    "类别": "category",
    "probability": "probability",
    "概率": "probability",
    "impact": "impact",
    "影响": "impact",
    "risk_score": "risk_score",
    "风险分数": "risk_score",
}

# 状态值映射
STATUS_MAP = {
    # Task状态
    "阻塞": "blocked",
    "blocked": "blocked",
    "待办": "todo",
    "todo": "todo",
    "进行中": "in_progress",
    "in_progress": "in_progress",
    "审查中": "in_review",
    "in_review": "in_review",
    "测试中": "testing",
    "testing": "testing",
    "已完成": "done",
    "完成": "done",
    "done": "done",
    "已取消": "cancelled",
    "cancelled": "cancelled",
    " backlog": "backlog",
    # Project状态
    "规划中": "planning",
    "planning": "planning",
    "活跃": "active",
    "active": "active",
    "暂停": "paused",
    "paused": "paused",
    "已完成项目": "completed",
    "completed": "completed",
    "已归档": "archived",
    "archived": "archived",
}

# 优先级映射
PRIORITY_MAP = {
    "最高": 1, "critical": 1, "紧急": 1, "highest": 1,
    "高": 2, "high": 2,
    "中": 3, "medium": 3, "normal": 3,
    "低": 4, "low": 4,
    "最低": 5, "lowest": 5,
}

# 实体键名标准化映射
ENTITY_KEY_MAP = {
    "task": "task", "任务": "task", "tasks": "task",
    "project": "project", "项目": "project", "projects": "project",
    "user": "user", "用户": "user", "users": "user",
    "member": "user", "成员": "user",
    "risk": "risk", "风险": "risk", "risks": "risk",
    "milestone": "milestone", "里程碑": "milestone", "milestones": "milestone",
    "comment": "comment", "评论": "comment", "comments": "comment",
}


def get_entity_key(entity: str) -> str:
    """获取标准化实体键名"""
    return ENTITY_KEY_MAP.get(entity, "task")


def get_model(entity: str, entity_models: Dict[str, Any]):
    """获取实体对应的SQLAlchemy模型"""
    key = get_entity_key(entity)
    return entity_models.get(key, Task)


def _safe_json_loads(text: str) -> Dict[str, Any]:
    """安全解析JSON（去除markdown代码块包裹）"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    import json
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}


async def match_user_by_name(db: AsyncSession, name: str) -> Optional[Dict[str, Any]]:
    """根据姓名模糊匹配用户"""
    if not name:
        return None

    # 精确匹配 full_name
    result = await db.execute(
        select(User).where(
            and_(User.is_active == True, func.lower(User.full_name) == name.lower())
        )
    )
    user = result.scalar_one_or_none()
    if user:
        return {"id": user.id, "full_name": user.full_name, "username": user.username}

    # 精确匹配 username
    result = await db.execute(
        select(User).where(
            and_(User.is_active == True, func.lower(User.username) == name.lower())
        )
    )
    user = result.scalar_one_or_none()
    if user:
        return {"id": user.id, "full_name": user.full_name, "username": user.username}

    # 模糊匹配 full_name
    result = await db.execute(
        select(User).where(
            and_(User.is_active == True, User.full_name.ilike(f"%{name}%"))
        )
    )
    user = result.scalar_one_or_none()
    if user:
        return {"id": user.id, "full_name": user.full_name, "username": user.username}

    return None


def serialize_model(obj) -> Dict[str, Any]:
    """将SQLAlchemy模型实例序列化为字典"""
    result = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name)
        if value is None:
            result[column.name] = None
        elif isinstance(value, datetime):
            result[column.name] = value.isoformat()
        elif isinstance(value, Decimal):
            result[column.name] = float(value)
        elif isinstance(value, enum.Enum):
            result[column.name] = value.value
        else:
            result[column.name] = value

    # 添加关联对象的基本信息
    if isinstance(obj, Task) and obj.assignee:
        result["assignee_name"] = obj.assignee.full_name or obj.assignee.username
    if isinstance(obj, Task) and obj.project:
        result["project_name"] = obj.project.name
    if isinstance(obj, Project) and obj.owner:
        result["owner_name"] = obj.owner.full_name or obj.owner.username
    if isinstance(obj, Risk) and obj.owner:
        result["owner_name"] = obj.owner.full_name or obj.owner.username
    if isinstance(obj, Milestone) and obj.project:
        result["project_name"] = obj.project.name
    if isinstance(obj, Comment) and obj.user:
        result["user_name"] = obj.user.full_name or obj.user.username
    if isinstance(obj, Comment) and obj.task:
        result["task_name"] = obj.task.name

    return result

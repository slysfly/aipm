"""
PMI中国AI项目管理社区 - AI自然语言查询执行引擎（NLP to SQL/API）
使用LLM将自然语言转换为结构化查询意图，并执行真实SQL查询

[CPMAI Phase: CPMAI Phase: Business Understanding | Domain: AI Fundamentals — NLP智能查询引擎]"""

import json
import re
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, cast, String, Numeric, DateTime, case
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import Select

from app.core.ai_engine import ai_engine
from app.models import User, Project, Task, TaskStatus, TaskPriority, Risk, Milestone, Comment


class NLPQueryEngine:
    """自然语言查询引擎：NLP -> 结构化查询计划 -> SQL执行 -> 自然语言摘要"""

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

    def __init__(self):
        self._entity_models = {
            "task": Task,
            "project": Project,
            "user": User,
            "risk": Risk,
            "milestone": Milestone,
            "comment": Comment,
        }

    async def parse_query(self, text: str) -> Dict[str, Any]:
        """
        解析自然语言查询为结构化查询意图
        
        示例：
        - "显示所有阻塞的高优先级任务" 
          → {entity: "task", filters: [...], sort: [...]}
        - "统计每个项目的任务完成率"
          → {entity: "task", filters: [], group_by: "project_id", aggregates: [...]}
        """
        if not text or not text.strip():
            raise ValueError("查询文本不能为空")

        system_prompt = """你是一个专业的数据查询解析助手。你的任务是将用户的自然语言查询转换为结构化的JSON查询计划。

请分析用户的查询意图，输出以下JSON格式：
{
  "entity": "task|project|user|risk|milestone|comment",
  "filters": [
    {"field": "字段名", "op": "eq|ne|gt|gte|lt|lte|like|in|between", "value": "值"}
  ],
  "sort": [
    {"field": "字段名", "direction": "asc|desc"}
  ],
  "group_by": "分组字段名或null",
  "aggregates": [
    {"field": "字段名", "op": "count|sum|avg|max|min", "alias": "结果别名", "condition": "可选条件如status=done"}
  ]或null,
  "limit": 数字或null,
  "joins": ["关联表名"]或null,
  "fields": ["要查询的字段"]或null
}

规则：
1. entity必须是：task, project, user, risk, milestone, comment
2. op操作符：eq(等于), ne(不等于), gt(大于), gte(大于等于), lt(小于), lte(小于等于), like(模糊匹配), in(在列表中), between(范围)
3. 时间值保持自然语言描述，如"本周一","上周","本月"等，后续会解析
4. 如果涉及负责人姓名，value写姓名，field用"assignee"
5. 聚合查询时，group_by填写分组字段
6. 如果查询"完成率"、"统计"等，使用aggregates
7. 只返回JSON，不要其他解释文字

示例1："显示所有阻塞的高优先级任务"
{
  "entity": "task",
  "filters": [
    {"field": "status", "op": "eq", "value": "blocked"},
    {"field": "priority", "op": "eq", "value": "high"}
  ],
  "sort": [{"field": "due_date", "direction": "asc"}],
  "group_by": null,
  "aggregates": null,
  "limit": null
}

示例2："统计每个项目的任务完成率"
{
  "entity": "task",
  "filters": [],
  "sort": null,
  "group_by": "project_id",
  "aggregates": [
    {"field": "id", "op": "count", "alias": "total"},
    {"field": "id", "op": "count", "alias": "completed", "condition": "status=done"}
  ],
  "limit": null
}

示例3："张三本周完成了多少任务"
{
  "entity": "task",
  "filters": [
    {"field": "assignee", "op": "eq", "value": "张三"},
    {"field": "status", "op": "eq", "value": "done"},
    {"field": "completed_at", "op": "gte", "value": "本周一"}
  ],
  "sort": null,
  "group_by": null,
  "aggregates": [
    {"field": "id", "op": "count", "alias": "count"}
  ],
  "limit": null
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请解析以下查询：\n\n{text}"},
        ]

        try:
            response = await ai_engine.chat(
                messages=messages,
                temperature=0.1,
                max_tokens=1500,
            )

            # 提取JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                query_plan = json.loads(json_match.group())
            else:
                # 尝试直接解析文本为JSON
                query_plan = json.loads(response.strip())

            # 后处理：标准化字段名、解析时间等
            query_plan = self._normalize_query_plan(query_plan)
            return query_plan

        except json.JSONDecodeError:
            # LLM没有返回有效JSON，使用降级解析
            return self._fallback_parse(text)
        except Exception as e:
            raise RuntimeError(f"查询解析失败: {str(e)}")

    def _normalize_query_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """标准化查询计划"""
        # 标准化实体名
        entity = plan.get("entity", "task").lower()
        if entity in self.ENTITY_MAP:
            entity = self._get_entity_key(entity)
        plan["entity"] = entity

        # 标准化filters中的字段名和值
        filters = plan.get("filters") or []
        for f in filters:
            field = f.get("field", "")
            # 映射字段名
            if field in self.FIELD_MAP:
                f["field"] = self.FIELD_MAP[field]
            # 映射状态值
            if field in ("status", "状态") and f.get("value"):
                val = str(f["value"]).lower()
                if val in self.STATUS_MAP:
                    f["value"] = self.STATUS_MAP[val]
            # 映射优先级值
            if field in ("priority", "优先级") and f.get("value"):
                val = str(f["value"]).lower()
                if val in self.PRIORITY_MAP:
                    f["value"] = self.PRIORITY_MAP[val]
            # 解析时间值
            if f.get("value") and isinstance(f["value"], str):
                parsed_time = self._parse_time_expression(f["value"])
                if parsed_time:
                    f["value"] = parsed_time

        # 标准化sort中的字段名
        sorts = plan.get("sort") or []
        for s in sorts:
            field = s.get("field", "")
            if field in self.FIELD_MAP:
                s["field"] = self.FIELD_MAP[field]
            # 解析时间排序字段
            if field in ("due_date", "截止日期", "截止时间"):
                s["field"] = "planned_end"
            if field in ("completed_at", "完成时间"):
                s["field"] = "actual_end"

        # 标准化group_by字段名
        group_by = plan.get("group_by")
        if group_by and group_by in self.FIELD_MAP:
            plan["group_by"] = self.FIELD_MAP[group_by]

        return plan

    def _parse_time_expression(self, text: str) -> Optional[str]:
        """解析时间表达式为ISO格式"""
        if not text or not isinstance(text, str):
            return None

        text = text.strip().lower()
        now = datetime.now()
        today = now.date()

        # 已经是ISO格式
        if re.match(r'^\d{4}-\d{2}-\d{2}', text):
            return text

        # 本周一
        if text in ("本周一", "本周一开始", "this monday"):
            days_since_monday = today.weekday()
            return (today - timedelta(days=days_since_monday)).isoformat()

        # 本周日
        if text in ("本周日", "this sunday"):
            days_until_sunday = 6 - today.weekday()
            return (today + timedelta(days=days_until_sunday)).isoformat()

        # 上周一
        if text in ("上周一", "last monday"):
            days_since_monday = today.weekday()
            return (today - timedelta(days=days_since_monday + 7)).isoformat()

        # 上周
        if text in ("上周", "last week"):
            return (today - timedelta(days=7)).isoformat()

        # 本月1日
        if text in ("本月", "本月1日", "this month"):
            return today.replace(day=1).isoformat()

        # 上月
        if text in ("上月", "上个月", "last month"):
            if today.month == 1:
                return today.replace(year=today.year - 1, month=12, day=1).isoformat()
            else:
                return today.replace(month=today.month - 1, day=1).isoformat()

        # 今天
        if text in ("今天", "today"):
            return today.isoformat()

        # 昨天
        if text in ("昨天", "yesterday"):
            return (today - timedelta(days=1)).isoformat()

        # 明天
        if text in ("明天", "tomorrow"):
            return (today + timedelta(days=1)).isoformat()

        # N天前
        days_ago_match = re.match(r'(\d+)\s*天前', text)
        if days_ago_match:
            days = int(days_ago_match.group(1))
            return (today - timedelta(days=days)).isoformat()

        # N天内
        days_within_match = re.match(r'(\d+)\s*天内', text)
        if days_within_match:
            days = int(days_within_match.group(1))
            return (today - timedelta(days=days)).isoformat()

        return None

    def _fallback_parse(self, text: str) -> Dict[str, Any]:
        """当LLM解析失败时的降级解析"""
        text_lower = text.lower()
        plan = {
            "entity": "task",
            "filters": [],
            "sort": None,
            "group_by": None,
            "aggregates": None,
            "limit": None,
        }

        # 识别实体
        if any(k in text_lower for k in ["项目", "project"]):
            plan["entity"] = "project"
        elif any(k in text_lower for k in ["用户", "成员", "user", "member", "人"]):
            plan["entity"] = "user"
        elif any(k in text_lower for k in ["风险", "risk"]):
            plan["entity"] = "risk"
        elif any(k in text_lower for k in ["里程碑", "milestone"]):
            plan["entity"] = "milestone"

        # 识别状态筛选
        for status_key, status_val in self.STATUS_MAP.items():
            if status_key in text_lower:
                plan["filters"].append({
                    "field": "status",
                    "op": "eq",
                    "value": status_val
                })
                break

        # 识别优先级筛选
        for pri_key, pri_val in self.PRIORITY_MAP.items():
            if pri_key in text_lower:
                plan["filters"].append({
                    "field": "priority",
                    "op": "eq",
                    "value": pri_val
                })
                break

        # 识别负责人
        assignee_match = re.search(r'([\u4e00-\u9fa5]{2,4})(?:负责|完成|的)', text)
        if assignee_match:
            plan["filters"].append({
                "field": "assignee",
                "op": "eq",
                "value": assignee_match.group(1)
            })

        # 识别统计/聚合
        if any(k in text_lower for k in ["统计", "多少", "count", "数量", "总数"]):
            plan["aggregates"] = [{"field": "id", "op": "count", "alias": "count"}]

        # 识别分组
        if "每个项目" in text or "按项目" in text:
            plan["group_by"] = "project_id"
        elif "每个人" in text or "按人" in text or "按负责人" in text:
            plan["group_by"] = "assignee_id"

        return plan

    def _get_entity_key(self, entity: str) -> str:
        """获取标准化实体键名"""
        mapping = {
            "task": "task", "任务": "task", "tasks": "task",
            "project": "project", "项目": "project", "projects": "project",
            "user": "user", "用户": "user", "users": "user",
            "member": "user", "成员": "user",
            "risk": "risk", "风险": "risk", "risks": "risk",
            "milestone": "milestone", "里程碑": "milestone", "milestones": "milestone",
            "comment": "comment", "评论": "comment", "comments": "comment",
        }
        return mapping.get(entity, "task")

    def _get_model(self, entity: str):
        """获取实体对应的SQLAlchemy模型"""
        key = self._get_entity_key(entity)
        return self._entity_models.get(key, Task)

    async def execute_query(
        self,
        query_plan: Dict[str, Any],
        db: AsyncSession,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行结构化查询计划，返回真实数据库查询结果
        """
        entity = query_plan.get("entity", "task")
        model = self._get_model(entity)
        filters = query_plan.get("filters") or []
        sorts = query_plan.get("sort") or []
        group_by = query_plan.get("group_by")
        aggregates = query_plan.get("aggregates")
        limit = query_plan.get("limit")

        start_time = time.time()

        # 构建基础查询
        stmt = select(model)

        # 处理关联加载（Task需要加载assignee和project）
        if model == Task:
            stmt = stmt.options(joinedload(Task.assignee), joinedload(Task.project))
        elif model == Project:
            stmt = stmt.options(joinedload(Project.owner))
        elif model == Risk:
            stmt = stmt.options(joinedload(Risk.owner))
        elif model == Milestone:
            stmt = stmt.options(joinedload(Milestone.project))
        elif model == Comment:
            stmt = stmt.options(joinedload(Comment.user), joinedload(Comment.task))

        # 应用project_id过滤（如果指定）
        if project_id and hasattr(model, "project_id"):
            stmt = stmt.where(model.project_id == project_id)

        # 应用filters
        where_conditions = []
        for f in filters:
            field_name = f.get("field", "")
            op = f.get("op", "eq")
            value = f.get("value")

            # 特殊处理assignee字段：需要模糊匹配用户
            if field_name == "assignee_id" and isinstance(value, str) and value:
                user_match = await self._match_user_by_name(db, value)
                if user_match:
                    value = user_match["id"]
                else:
                    # 用户不存在，返回空结果
                    return {
                        "data": [],
                        "columns": [],
                        "total": 0,
                        "is_aggregate": False,
                        "execution_time_ms": 0,
                    }

            # 获取模型字段
            column = getattr(model, field_name, None)
            if column is None:
                continue

            condition = self._build_condition(column, op, value)
            if condition is not None:
                where_conditions.append(condition)

        if where_conditions:
            stmt = stmt.where(and_(*where_conditions))

        # 处理软删除
        if hasattr(model, "is_deleted"):
            stmt = stmt.where(model.is_deleted == False)

        # 处理聚合查询
        if aggregates:
            return await self._execute_aggregate_query(
                db, model, filters, group_by, aggregates, project_id, where_conditions
            )

        # 应用排序
        for s in sorts:
            field_name = s.get("field", "")
            direction = s.get("direction", "asc")
            column = getattr(model, field_name, None)
            if column is not None:
                if direction == "desc":
                    stmt = stmt.order_by(desc(column))
                else:
                    stmt = stmt.order_by(asc(column))

        # 如果没有指定排序，使用默认排序
        if not sorts:
            if hasattr(model, "created_at"):
                stmt = stmt.order_by(desc(model.created_at))
            elif hasattr(model, "id"):
                stmt = stmt.order_by(desc(model.id))

        # 应用limit
        if limit:
            stmt = stmt.limit(limit)
        else:
            # 默认限制1000条防止过大查询
            stmt = stmt.limit(1000)

        # 执行查询
        result = await db.execute(stmt)
        rows = result.unique().scalars().all()

        # 转换为可序列化的字典列表
        data = []
        for row in rows:
            data.append(self._serialize_model(row))

        execution_time = (time.time() - start_time) * 1000

        # 提取列名
        columns = list(data[0].keys()) if data else []

        return {
            "data": data,
            "columns": columns,
            "total": len(data),
            "is_aggregate": False,
            "execution_time_ms": round(execution_time, 2),
        }

    async def _execute_aggregate_query(
        self,
        db: AsyncSession,
        model,
        filters: List[Dict],
        group_by: Optional[str],
        aggregates: List[Dict],
        project_id: Optional[str],
        where_conditions: List
    ) -> Dict[str, Any]:
        """执行聚合查询"""
        start_time = time.time()

        # 构建SELECT子句
        select_columns = []
        group_column = None

        if group_by:
            group_column = getattr(model, group_by, None)
            if group_column is not None:
                select_columns.append(group_column.label(group_by))

        for agg in aggregates:
            field = agg.get("field", "id")
            op = agg.get("op", "count")
            alias = agg.get("alias", f"{op}_{field}")
            condition = agg.get("condition")

            column = getattr(model, field, None)
            if column is None:
                column = model.id

            # 处理带条件的聚合（如 status=done 的计数）
            if condition:
                agg_column = self._build_conditional_aggregate(column, op, condition, model)
            else:
                agg_column = self._build_aggregate_column(column, op)

            if agg_column is not None:
                select_columns.append(agg_column.label(alias))

        if not select_columns:
            # 没有有效聚合，返回count(*)
            select_columns.append(func.count().label("total"))

        stmt = select(*select_columns)

        # 应用where条件
        if where_conditions:
            stmt = stmt.where(and_(*where_conditions))

        # 应用project_id
        if project_id and hasattr(model, "project_id"):
            stmt = stmt.where(model.project_id == project_id)

        # 软删除
        if hasattr(model, "is_deleted"):
            stmt = stmt.where(model.is_deleted == False)

        # 分组
        if group_column is not None:
            stmt = stmt.group_by(group_column)

        result = await db.execute(stmt)
        rows = result.all()

        # 转换为字典列表
        data = []
        for row in rows:
            row_dict = {}
            if group_by:
                row_dict[group_by] = row[0]
                for i, agg in enumerate(aggregates):
                    alias = agg.get("alias", f"agg_{i}")
                    row_dict[alias] = row[i + 1]
            else:
                for i, agg in enumerate(aggregates):
                    alias = agg.get("alias", f"agg_{i}")
                    row_dict[alias] = row[i]
            data.append(row_dict)

        execution_time = (time.time() - start_time) * 1000

        columns = list(data[0].keys()) if data else []

        return {
            "data": data,
            "columns": columns,
            "total": len(data),
            "is_aggregate": True,
            "execution_time_ms": round(execution_time, 2),
        }

    def _build_condition(self, column, op: str, value):
        """构建SQLAlchemy条件表达式"""
        if value is None:
            return None

        op = op.lower()

        if op == "eq":
            return column == value
        elif op == "ne":
            return column != value
        elif op == "gt":
            return column > value
        elif op == "gte":
            return column >= value
        elif op == "lt":
            return column < value
        elif op == "lte":
            return column <= value
        elif op == "like":
            return column.ilike(f"%{value}%")
        elif op == "in":
            if isinstance(value, list):
                return column.in_(value)
            return None
        elif op == "between":
            if isinstance(value, list) and len(value) == 2:
                return column.between(value[0], value[1])
            return None
        return None

    def _build_aggregate_column(self, column, op: str):
        """构建聚合列"""
        op = op.lower()
        if op == "count":
            return func.count(column)
        elif op == "sum":
            return func.sum(column)
        elif op == "avg":
            return func.avg(column)
        elif op == "max":
            return func.max(column)
        elif op == "min":
            return func.min(column)
        return func.count(column)

    def _build_conditional_aggregate(self, column, op: str, condition: str, model):
        """构建带条件的聚合（如count where status=done）"""
        # 解析 condition 如 "status=done"
        match = re.match(r'(\w+)=(.+)', condition)
        if not match:
            return self._build_aggregate_column(column, op)

        cond_field, cond_value = match.groups()
        cond_column = getattr(model, cond_field, None)
        if cond_column is None:
            return self._build_aggregate_column(column, op)

        # 使用case when实现条件聚合
        op = op.lower()
        if op == "count":
            return func.sum(case((cond_column == cond_value, 1), else_=0))
        elif op == "sum":
            return func.sum(case((cond_column == cond_value, column), else_=0))
        return func.count(column)

    async def _match_user_by_name(self, db: AsyncSession, name: str) -> Optional[Dict[str, Any]]:
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

    def _serialize_model(self, obj) -> Dict[str, Any]:
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

    async def generate_summary(self, results: Dict[str, Any], original_text: str) -> str:
        """
        使用LLM将查询结果转换为人类可读的自然语言摘要
        """
        data = results.get("data", [])
        total = results.get("total", 0)
        is_aggregate = results.get("is_aggregate", False)

        if not data:
            return f"未找到符合「{original_text}」条件的数据。"

        # 构建结果摘要上下文
        result_preview = json.dumps(data[:20], ensure_ascii=False, default=str)

        system_prompt = """你是一个数据分析助手。请根据用户的原始查询和查询结果，生成一段简洁、自然的中文摘要。

要求：
1. 直接回答用户的问题，不要重复查询条件
2. 使用自然、口语化的中文
3. 如果结果是聚合数据，总结关键数字和趋势
4. 如果结果是列表，说明总数和关键信息
5. 控制在100字以内
6. 不要提及技术细节（如SQL、数据库等）"""

        user_prompt = f"""用户查询：{original_text}

查询结果（共{total}条）：
{result_preview}

请生成一段自然语言摘要："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            summary = await ai_engine.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=300,
            )
            return summary.strip()
        except Exception:
            # 降级：生成简单摘要
            if is_aggregate:
                return f"查询完成，共获得 {total} 条聚合数据。"
            else:
                return f"查询完成，共找到 {total} 条符合条件的数据。"


# 全局查询引擎实例
nlp_query_engine = NLPQueryEngine()

# 导入enum用于序列化
import enum
"""
PMI中国AI项目管理社区 - NLP查询执行模块
执行结构化查询计划，返回真实数据库查询结果
"""

import time
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, asc
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import Select

from app.models import Task, Project, User, Risk, Milestone, Comment
from .helpers import (
    get_model, match_user_by_name, serialize_model
)
from .conditions import build_condition, build_aggregate_column, build_conditional_aggregate


async def execute_query(
    engine,
    query_plan: Dict[str, Any],
    db: AsyncSession,
    project_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    执行结构化查询计划，返回真实数据库查询结果
    """
    entity = query_plan.get("entity", "task")
    model = get_model(entity, engine._entity_models)
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
            user_match = await match_user_by_name(db, value)
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

        condition = build_condition(column, op, value)
        if condition is not None:
            where_conditions.append(condition)

    if where_conditions:
        stmt = stmt.where(and_(*where_conditions))

    # 处理软删除
    if hasattr(model, "is_deleted"):
        stmt = stmt.where(model.is_deleted == False)

    # 处理聚合查询
    if aggregates:
        return await _execute_aggregate_query(
            engine, db, model, filters, group_by, aggregates, project_id, where_conditions
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
        data.append(serialize_model(row))

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
    engine,
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
            agg_column = build_conditional_aggregate(column, op, condition, model)
        else:
            agg_column = build_aggregate_column(column, op)

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

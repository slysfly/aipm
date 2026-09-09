"""
PMI中国AI项目管理社区 - NLP查询条件构建模块
构建SQLAlchemy条件表达式和聚合列
"""

import re
from typing import List, Optional

from sqlalchemy import func, case


def build_condition(column, op: str, value):
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


def build_aggregate_column(column, op: str):
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


def build_conditional_aggregate(column, op: str, condition: str, model):
    """构建带条件的聚合（如count where status=done）"""
    # 解析 condition 如 "status=done"
    match = re.match(r'(\w+)=(.+)', condition)
    if not match:
        return build_aggregate_column(column, op)

    cond_field, cond_value = match.groups()
    cond_column = getattr(model, cond_field, None)
    if cond_column is None:
        return build_aggregate_column(column, op)

    # 使用case when实现条件聚合
    op = op.lower()
    if op == "count":
        return func.sum(case((cond_column == cond_value, 1), else_=0))
    elif op == "sum":
        return func.sum(case((cond_column == cond_value, column), else_=0))
    return func.count(column)

"""
PMI中国AI项目管理社区 - NLP查询解析模块
使用LLM将自然语言转换为结构化查询计划
"""

import json
import re
from typing import Dict, Any, Optional

from app.core.ai_engine import ai_engine
from .helpers import ENTITY_MAP, FIELD_MAP, STATUS_MAP, PRIORITY_MAP
from .time_parser import parse_time_expression


SYSTEM_PROMPT = """你是一个专业的数据查询解析助手。你的任务是将用户的自然语言查询转换为结构化的JSON查询计划。

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


async def parse_query(engine, text: str) -> Dict[str, Any]:
    """
    解析自然语言查询为结构化查询意图
    使用LLM进行智能解析，失败时降级到规则解析
    """
    if not text or not text.strip():
        raise ValueError("查询文本不能为空")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
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
        query_plan = _normalize_query_plan(engine, query_plan)
        return query_plan

    except json.JSONDecodeError:
        # LLM没有返回有效JSON，使用降级解析
        return _fallback_parse(engine, text)
    except Exception as e:
        raise RuntimeError(f"查询解析失败: {str(e)}")


def _normalize_query_plan(engine, plan: Dict[str, Any]) -> Dict[str, Any]:
    """标准化查询计划"""
    # 标准化实体名
    entity = plan.get("entity", "task").lower()
    if entity in ENTITY_MAP:
        entity = _get_entity_key(entity)
    plan["entity"] = entity

    # 标准化filters中的字段名和值
    filters = plan.get("filters") or []
    for f in filters:
        field = f.get("field", "")
        # 映射字段名
        if field in FIELD_MAP:
            f["field"] = FIELD_MAP[field]
        # 映射状态值
        if field in ("status", "状态") and f.get("value"):
            val = str(f["value"]).lower()
            if val in STATUS_MAP:
                f["value"] = STATUS_MAP[val]
        # 映射优先级值
        if field in ("priority", "优先级") and f.get("value"):
            val = str(f["value"]).lower()
            if val in PRIORITY_MAP:
                f["value"] = PRIORITY_MAP[val]
        # 解析时间值
        if f.get("value") and isinstance(f["value"], str):
            parsed_time = parse_time_expression(f["value"])
            if parsed_time:
                f["value"] = parsed_time

    # 标准化sort中的字段名
    sorts = plan.get("sort") or []
    for s in sorts:
        field = s.get("field", "")
        if field in FIELD_MAP:
            s["field"] = FIELD_MAP[field]
        # 解析时间排序字段
        if field in ("due_date", "截止日期", "截止时间"):
            s["field"] = "planned_end"
        if field in ("completed_at", "完成时间"):
            s["field"] = "actual_end"

    # 标准化group_by字段名
    group_by = plan.get("group_by")
    if group_by and group_by in FIELD_MAP:
        plan["group_by"] = FIELD_MAP[group_by]

    return plan


def _fallback_parse(engine, text: str) -> Dict[str, Any]:
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
    for status_key, status_val in STATUS_MAP.items():
        if status_key in text_lower:
            plan["filters"].append({
                "field": "status",
                "op": "eq",
                "value": status_val
            })
            break

    # 识别优先级筛选
    for pri_key, pri_val in PRIORITY_MAP.items():
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


def _get_entity_key(entity: str) -> str:
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

"""
PMI中国AI项目管理社区 - NLP时间表达式解析模块
将自然语言时间描述解析为ISO格式
"""

import re
from datetime import datetime, timedelta
from typing import Optional


def parse_time_expression(text: str) -> Optional[str]:
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

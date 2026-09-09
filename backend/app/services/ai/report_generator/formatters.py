"""JSON 提取与格式化工具函数"""

import json
import re
from typing import Dict, Any


def extract_json(text: str) -> Dict[str, Any]:
    """从 AI 响应文本中提取并解析 JSON 对象。"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group(0)

    return json.loads(text)


def safe_json_loads(text: str, default: Dict[str, Any]) -> Dict[str, Any]:
    """安全加载 JSON，失败时返回默认值。"""
    try:
        return extract_json(text)
    except (json.JSONDecodeError, ValueError):
        return default

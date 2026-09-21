"""
大模型 JSON 输出解析（带截断修复）。

为什么需要
----------
「AI 帮我填」原先用 ai_service._safe_json_loads：解析失败就返回 {}，
调用方无法区分「模型没建议」和「模型输出坏了」，前端统一显示「暂无可补全项」——
用户看到的是「点了没反应」，而且没有任何可排查的线索。

更常见的一种坏输出是**被 max_tokens 截断**：模型正写到一半预算用尽，
JSON 末尾缺少收尾的引号与括号。这种情况只要补上括号就能救回大部分字段，
没有必要整单丢弃。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_+-]*\s*")


def strip_fences(text: str) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = _FENCE_RE.sub("", raw)
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
    return raw.strip()


def _scan(body: str) -> Tuple[Optional[int], List[str], bool]:
    """扫描 JSON 文本。

    返回 (完整对象结束下标或 None, 未闭合的收尾字符栈, 结束时是否仍在字符串内)。
    """
    stack: List[str] = []
    in_str = False
    esc = False
    end: Optional[int] = None
    for i, ch in enumerate(body):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
                if not stack:
                    end = i
                    break
    return end, stack, in_str


def _balance(body: str) -> str:
    """补齐未闭合的字符串/括号，并去掉悬空的逗号。"""
    _end, stack, in_str = _scan(body)
    out = body
    if in_str:
        # 末尾可能停在转义符上
        if out.endswith("\\") and not out.endswith("\\\\"):
            out = out[:-1]
        out += '"'
    out = out.rstrip()
    while out.endswith(","):
        out = out[:-1].rstrip()
    out += "".join(reversed(stack))
    return out


def parse_llm_json(text: str) -> Tuple[Optional[Any], Optional[str]]:
    """解析大模型返回的 JSON。

    返回 (parsed, note)：parsed 为 None 表示彻底失败，note 说明原因或修复方式。
    """
    if not text or not isinstance(text, str):
        return None, "模型返回为空"

    raw = strip_fences(text)

    try:
        return json.loads(raw), None
    except (json.JSONDecodeError, ValueError):
        pass

    start = raw.find("{")
    alt = raw.find("[")
    if start == -1 or (alt != -1 and alt < start):
        start = alt
    if start == -1:
        return None, "模型输出不含 JSON 对象"

    body = raw[start:]
    end, _stack, _in_str = _scan(body)
    if end is not None:
        try:
            return json.loads(body[: end + 1]), None
        except (json.JSONDecodeError, ValueError):
            pass

    # 截断修复：从后往前找可用的切分点，补全括号后重试
    cuts = [i for i, ch in enumerate(body) if ch in ",}"] or []
    for i in reversed(cuts[-80:]):
        try:
            parsed = json.loads(_balance(body[: i + 1]))
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, (dict, list)):
            logger.info("LLM JSON 输出被截断，已修复（原长 %d 字符）", len(raw))
            return parsed, "json_truncated_repaired"

    return None, "模型输出不是合法 JSON"

"""
变更控制执行器（Change Control Executor）

职责：审批通过（status → approved）后，按 change_items 列表把每一条"由什么变为什么"
真正落地到对应实体（project / task / milestone），落地后立即再读回校验，
确保变更准确有效。

安全设计：
- 仅允许更新白名单字段，杜绝任意属性写入。
- 实体必须属于本变更请求所关联的项目，防止跨项目误改。
- 类型按字段强制（date / number / bool / string），无法转换即标记失败。
- 写入后立即重读并字符串比对；不一致则 verified=False，记录实际值与差异。

返回 execution_log 列表（每条变更项一个条目），由路由层写入 ChangeRequest。
"""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pm_extras import ChangeRequest
from app.models import Project, Task, Milestone


# ── 白名单：每种实体允许变更的字段及类型 ──────────────────────────────────────
# label 用于前端展示；kind 用于类型强制；enum 用于状态/优先级取值校验（可选）
_FIELDS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "project": {
        "name":        {"label": "项目名称",   "kind": "string"},
        "description": {"label": "项目描述",   "kind": "string"},
        "start_date":  {"label": "计划开始日", "kind": "date"},
        "end_date":    {"label": "计划结束日", "kind": "date"},
        "budget":      {"label": "预算(¥)",   "kind": "decimal"},
        "priority":    {"label": "优先级",     "kind": "int", "min": 1, "max": 5},
        "status":      {"label": "项目状态",   "kind": "enum",
                        "options": ["planning", "in_progress", "on_hold", "completed", "cancelled"]},
    },
    "task": {
        "name":            {"label": "任务名称", "kind": "string"},
        "description":     {"label": "任务描述", "kind": "string"},
        "planned_start":   {"label": "计划开始", "kind": "datetime"},
        "planned_end":     {"label": "计划结束", "kind": "datetime"},
        "estimated_hours": {"label": "预估工时", "kind": "decimal"},
        "progress":        {"label": "进度(%)",  "kind": "decimal", "min": 0, "max": 100},
        "priority":        {"label": "优先级",   "kind": "int", "min": 1, "max": 5},
        "status":          {"label": "任务状态", "kind": "enum",
                            "options": ["todo", "in_progress", "doing", "done", "blocked", "review", "testing"]},
    },
    "milestone": {
        "name":        {"label": "里程碑名称", "kind": "string"},
        "description": {"label": "里程碑描述", "kind": "string"},
        "due_date":    {"label": "截止日期",   "kind": "date"},
        "status":      {"label": "状态",       "kind": "enum",
                        "options": ["pending", "completed", "delayed"]},
    },
}

_ENTITY_MODELS = {
    "project": Project,
    "task": Task,
    "milestone": Milestone,
}

# 各实体的项目归属字段（用于跨项目防护）
_ENTITY_PROJECT_FIELD = {
    "project": "id",           # 项目自身用 id == change.project_id
    "task": "project_id",
    "milestone": "project_id",
}


def _coerce(kind: str, raw: Any, spec: Dict[str, Any]) -> Tuple[Any, str | None]:
    """按字段类型强制；返回 (转换后值, 错误信息)。"""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None, "新值为空"
    s = str(raw).strip()
    try:
        if kind == "string":
            return s, None
        if kind == "int":
            v = int(Decimal(s))
            if "min" in spec and v < spec["min"]:
                return None, f"值 {v} 小于最小值 {spec['min']}"
            if "max" in spec and v > spec["max"]:
                return None, f"值 {v} 大于最大值 {spec['max']}"
            return v, None
        if kind == "decimal":
            return Decimal(s), None
        if kind == "bool":
            if s.lower() in ("true", "1", "yes", "on"):
                return True, None
            if s.lower() in ("false", "0", "no", "off"):
                return False, None
            return None, "布尔值应为 true/false"
        if kind == "date":
            return date.fromisoformat(s), None
        if kind == "datetime":
            # 接受 "YYYY-MM-DD" 或 "YYYY-MM-DDTHH:MM:SS"
            try:
                return datetime.fromisoformat(s), None
            except ValueError:
                return datetime.fromisoformat(s + "T00:00:00"), None
        if kind == "enum":
            opts = spec.get("options", [])
            if s not in opts:
                return None, f"取值 {s!r} 不在允许范围 {opts}"
            return s, None
    except (InvalidOperation, ValueError) as e:
        return None, f"类型转换失败: {e}"
    return None, f"未知字段类型 {kind}"


async def execute_approved_change(
    db: AsyncSession,
    change: ChangeRequest,
) -> List[Dict[str, Any]]:
    """审批通过后执行变更；返回 execution_log（持久化由调用方写入）。"""
    items: List[Dict[str, Any]] = list(change.change_items or [])
    log: List[Dict[str, Any]] = []

    for item in items:
        entry: Dict[str, Any] = {
            "scope": item.get("scope") or "",
            "entity_type": item.get("entity_type") or "",
            "entity_id": item.get("entity_id") or "",
            "field": item.get("field") or "",
            "before": item.get("before"),
            "after": item.get("after"),
            "applied": False,
            "verified": False,
            "applied_at": "",
            "error": "",
        }
        et = entry["entity_type"]
        eid = entry["entity_id"]
        field = entry["field"]

        # 1. 实体类型与字段必须在白名单内
        spec_dict = _FIELDS.get(et)
        if not spec_dict:
            entry["error"] = f"未知实体类型 {et!r}"
            log.append(entry); continue
        spec = spec_dict.get(field)
        if not spec:
            entry["error"] = f"字段 {field!r} 不在 {et} 的可变更白名单"
            log.append(entry); continue

        # 2. 查找实体
        model = _ENTITY_MODELS[et]
        obj = await db.get(model, eid)
        if not obj:
            entry["error"] = f"{et}({eid}) 不存在"
            log.append(entry); continue

        # 3. 跨项目防护
        owner_field = _ENTITY_PROJECT_FIELD[et]
        owner_id = getattr(obj, owner_field, None)
        if str(owner_id) != str(change.project_id or ""):
            entry["error"] = f"实体不属于本变更请求所关联的项目（拒绝跨项目写入）"
            log.append(entry); continue

        # 4. 类型强制
        new_val, err = _coerce(spec["kind"], entry["after"], spec)
        if err:
            entry["error"] = err
            log.append(entry); continue

        # 5. 写入
        try:
            setattr(obj, field, new_val)
            await db.commit()
            await db.refresh(obj)
        except Exception as e:
            await db.rollback()
            entry["error"] = f"写入异常: {e}"
            log.append(entry); continue
        entry["applied"] = True

        # 6. 再读回校验（按字段类型稳健比对，容忍 Decimal 精度/时区差异）
        try:
            current = getattr(obj, field)
            if _values_equal(spec["kind"], new_val, current):
                entry["verified"] = True
            else:
                entry["verified"] = False
                entry["error"] = (
                    f"读回校验失败：期望 {_stringify(new_val)!r}，"
                    f"实为 {_stringify(current)!r}"
                )
            entry["applied_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception as e:
            entry["error"] = f"校验异常: {e}"
            entry["applied_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        log.append(entry)

    return log


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def _to_naive_dt(v: Any) -> datetime:
    """把任意日期/时间/字符串统一成 naive datetime，便于比对。"""
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    s = str(v).strip()
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.fromisoformat(s + "T00:00:00")


def _values_equal(kind: str, expected: Any, actual: Any) -> bool:
    """按字段类型稳健比对写入结果，容忍 Decimal 精度与 datetime 时区差异。"""
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    try:
        if kind in ("decimal",):
            return Decimal(str(expected)) == Decimal(str(actual))
        if kind == "int":
            return int(expected) == int(actual)
        if kind == "bool":
            return bool(expected) == bool(actual)
        if kind == "date":
            return _to_naive_dt(expected).date() == _to_naive_dt(actual).date()
        if kind == "datetime":
            return _to_naive_dt(expected) == _to_naive_dt(actual)
        # string / enum
        return str(expected) == str(actual)
    except Exception:
        return str(expected) == str(actual)


def get_field_whitelist() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """供前端拉取可变更字段清单（label + kind + enum options）。"""
    return _FIELDS
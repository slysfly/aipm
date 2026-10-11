"""把数据库里的「人话」补进 AI 上下文。

## 为什么需要这个模块（2026-09-19 线上实测）

前端调用「AI 帮我填」时只传了一个 UUID：

    {"form_type": "task",
     "fields":  {"project_id": "67b89883-…", "status": "todo", "priority": 3},
     "context": {"project_id": ""}}          ← 实测里是空串

模型手里没有任何关于"这个任务是什么"的信息，而 prompt 里明确要求
"不要编造无法从上下文推断的具体信息"，于是它**正确地拒绝了**，返回 {}。
线上 4 次调用里 3 次返回 0 个字段 —— 用户看到的就是"点了没反应"。

本模块负责用 project_id / sprint_id 反查出**项目名、项目描述、同项目已有条目名**，
让模型有料可依据。

## 设计约束

1. **只读**，绝不写库。
2. **失败必须静默降级**：补上下文失败就返回原 context，不能把主流程搞挂。
3. **严格限量**：本项目网关首字延迟 2~8.9s，上下文越长模型越慢。
   所以同类条目最多 8 条、每段文本最多 120 字。
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select

logger = logging.getLogger(__name__)

MAX_SIBLING_ITEMS = 8
MAX_TEXT_LEN = 120
MAX_LIST_ITEM_LEN = 40


def _clip(value: Any, limit: int = MAX_TEXT_LEN) -> str:
    """把任意值压成干净的短字符串。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = " ".join(text.split())  # 折叠换行与连续空白
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def _pick_id(*sources: Any) -> Optional[str]:
    """从多个 dict 里挑出第一个非空的 id（字符串）。"""
    for src in sources:
        if not isinstance(src, dict):
            continue
        for key in ("project_id", "sprint_id", "parent_task_id"):
            val = src.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _field_id(fields: Dict[str, Any], key: str) -> Optional[str]:
    val = (fields or {}).get(key)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


async def _load_project(db, project_id: str) -> Optional[Dict[str, Any]]:
    from app.models import Project

    row = (
        await db.execute(
            select(Project.name, Project.description, Project.industry_type, Project.status)
            .where(Project.id == project_id)
        )
    ).first()
    if row is None:
        return None
    return {
        "project_name": _clip(row[0], 80),
        "project_description": _clip(row[1]),
        "project_industry": _clip(row[2], 40),
        "project_status": _clip(row[3], 20),
    }


async def _load_sibling_tasks(db, project_id: str, exclude_task_id: Optional[str]) -> List[str]:
    """同项目下已有任务名 —— 给模型"这个项目在做什么"的语感。"""
    from app.models import Task

    stmt = select(Task.name).where(Task.project_id == project_id)
    if exclude_task_id:
        stmt = stmt.where(Task.id != exclude_task_id)
    stmt = stmt.order_by(Task.created_at.desc()).limit(MAX_SIBLING_ITEMS)
    rows = (await db.execute(stmt)).scalars().all()
    names: List[str] = []
    for n in rows:
        clipped = _clip(n, MAX_LIST_ITEM_LEN)
        if clipped and clipped not in names:
            names.append(clipped)
    return names


async def _load_sprint(db, sprint_id: str) -> Optional[Dict[str, Any]]:
    from app.models.sprint import Sprint

    row = (
        await db.execute(select(Sprint.name, Sprint.goal).where(Sprint.id == sprint_id))
    ).first()
    if row is None:
        return None
    return {"sprint_name": _clip(row[0], 80), "sprint_goal": _clip(row[1])}


async def _load_parent_task(db, task_id: str) -> Optional[Dict[str, Any]]:
    from app.models import Task

    row = (await db.execute(select(Task.name).where(Task.id == task_id))).first()
    if row is None:
        return None
    return {"parent_task_name": _clip(row[0], 80)}


async def enrich_context(
    form_type: str,
    fields: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """返回补全后的上下文（原 context + 从库里查到的"人话"）。

    任何异常都被吞掉并记日志 —— 补上下文只是锦上添花，绝不能拖垮主流程。
    """
    fields = fields or {}
    context = dict(context or {})

    # 已经在 context 里给了项目名就不必再查（前端将来若直接传名称，这里自动跳过）
    if _clip(context.get("project_name")):
        return context

    project_id = _field_id(fields, "project_id") or _clip(context.get("project_id")) or None
    sprint_id = _field_id(fields, "sprint_id")
    parent_task_id = _field_id(fields, "parent_task_id")

    if not project_id and not sprint_id:
        return context

    try:
        from app.db.session import async_session_maker

        async with async_session_maker() as db:
            if sprint_id and not project_id:
                sprint = await _load_sprint(db, sprint_id)
                if sprint:
                    context.update(sprint)

            if project_id:
                project = await _load_project(db, project_id)
                if project:
                    context.update(project)

                if form_type == "task":
                    siblings = await _load_sibling_tasks(db, project_id, None)
                    if siblings:
                        context["sibling_tasks"] = siblings

            if form_type == "task" and parent_task_id:
                parent = await _load_parent_task(db, parent_task_id)
                if parent:
                    context.update(parent)

            if form_type == "task" and sprint_id:
                sprint = await _load_sprint(db, sprint_id)
                if sprint:
                    context.update(sprint)

    except Exception as exc:  # noqa: BLE001 - 补上下文失败不应影响主流程
        logger.warning("assist_fill 上下文补全失败（已降级为原 context）: %s", exc)
        return dict(context or {})

    # 去掉空值，避免把 {"project_name": ""} 这类噪声喂给模型
    return {k: v for k, v in context.items() if v not in ("", None, [], {})}


def has_usable_signal(form_type: str, fields: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """判断「有没有依据让模型产出内容」。

    没有依据就不该调模型 —— 本项目网关一次调用要等 2~9 秒，
    花 9 秒换一句"我编不出来"是最差的体验。

    判据：存在任一非空文本字段，或上下文里有任何可用于推断的文本/列表。
    """
    fields = fields or {}
    context = context or {}

    # 1) 表单里已经有文本内容（用户写了点什么）
    for key in ("name", "title", "description", "goal", "content", "summary", "remark"):
        if _clip(fields.get(key)):
            return True

    # 2) 上下文里有可依据的文本
    for key in (
        "project_name",
        "project_description",
        "sprint_name",
        "sprint_goal",
        "parent_task_name",
    ):
        if _clip(context.get(key)):
            return True

    # 3) 上下文里有同类条目名列表
    for key in ("sibling_tasks", "existing_items", "related_items"):
        val = context.get(key)
        if isinstance(val, (list, tuple)) and any(_clip(x) for x in val):
            return True

    return False


NO_SIGNAL_MESSAGE = "先填个名称，或选择所属项目，我就能帮你补全其余字段"


def has_cheap_signal(form_type: str, fields: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """不查库的快速判据，供 API 层在**建任务之前**判断要不要拦下。

    与 has_usable_signal 的区别：这里额外把「带了 project_id / sprint_id」
    也算作有信号 —— 因为查库后大概率能拿到项目名，交给服务层再判一次即可。
    这样 API 层能在完全空白的请求上省掉一次建任务 + 一次 2~9 秒的模型调用。
    """
    if has_usable_signal(form_type, fields, context):
        return True

    for src in (fields or {}, context or {}):
        for key in ("project_id", "sprint_id", "parent_task_id"):
            val = src.get(key)
            if isinstance(val, str) and val.strip():
                return True
    return False


def no_signal_result(form_type: str, instant: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """没有依据时的即时返回（0ms，不调模型）。"""
    result: Dict[str, Any] = {
        "suggestions": {},
        "improve_tips": [],
        "form_type": form_type,
        "error": "need_input",
        "message": NO_SIGNAL_MESSAGE,
    }
    if instant:
        result["instant"] = instant
    return result

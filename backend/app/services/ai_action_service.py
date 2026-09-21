"""AI 操作执行服务：把 chat() 解析出的 actions 真正写入数据库。

设计要点：
- 幂等：client_token 唯一索引，重复确认返回首次结果，不重复写库。
- 双层事务：业务写库用 ``db.begin_nested()`` 存点，单条失败回滚该条但不影响同批其它条；
  执行日志始终在外层事务提交（即便业务全失败也要落日志）。
- 一张卡片（一个 client_token）对应一行 AIActionLog：results 为全部 action 的执行明细列表。
- 跨项目越权：update_task_status 的目标任务必须属于 project_id，否则该条记 AUTH_DENIED。
- 乐观锁：update 时同步自增 task.version。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskStatus
from app.models.ai_action_log import AIActionLog

logger = logging.getLogger(__name__)

# update_task_status 允许写入的 status 白名单（与 TaskStatus 枚举 value 对齐）
_VALID_STATUS = {s.value for s in TaskStatus}


async def _resolve_task(db: AsyncSession, project_id: str, task_ref: str) -> Optional[Task]:
    """解析目标任务：① 完整 36 位 UUID；② 8 位短 ID（允许带 # 前缀）前缀匹配；③ 失败返回 None。

    前缀匹配若命中 **多个** 任务，不再静默取首条（旧 `LIMIT 1` 会在前缀碰撞时选错任务），
    而是抛 ``AMBIGUOUS``，交由调用方按「单条失败」处理——宁可失败也不改错任务。
    """
    if not task_ref:
        return None
    ref = task_ref.strip()
    # ① 完整 UUID
    task = await db.get(Task, ref)
    if task is not None:
        return task
    # ② 8 位短 ID（允许带 # 前缀）
    short = ref[1:] if ref.startswith("#") else ref
    if len(short) >= 8:
        matches = (
            await db.execute(
                select(Task)
                .where(Task.id.like(f"{short}%"))
                .order_by(Task.created_at.asc(), Task.id.asc())
                .limit(2)
            )
        ).scalars().all()
        if len(matches) == 1:
            return matches[0]
        if len(matches) >= 2:
            raise ValueError(
                f"AMBIGUOUS: 短 ID '{short}' 匹配到 {len(matches)}+ 个任务，请用完整 UUID 或更长的短 ID 指认"
            )
    return None


def _validate_create(act: Dict[str, Any]) -> None:
    name = (act.get("name") or "").strip()
    if not name:
        raise ValueError("INVALID: create_task 的 name 不能为空")
    status = act.get("status")
    if status is not None and status not in _VALID_STATUS:
        raise ValueError(f"INVALID_STATUS: {status} 不在允许范围 {sorted(_VALID_STATUS)}")


def _parse_date(v: Any) -> Optional[datetime]:
    """把 LLM 输出的 YYYY-MM-DD（或带时间）解析为 naive datetime；非法值返回 None 不抛异常。"""
    if not isinstance(v, str) or not v.strip():
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(v.strip(), fmt)
        except ValueError:
            continue
    return None


async def _do_create_task(db: AsyncSession, project_id: str, act: Dict[str, Any]) -> Task:
    """在 db.begin_nested() 存点内创建任务；失败由调用方 try/except 捕获并回滚该存点。"""
    async with db.begin_nested():
        cnt = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.project_id == project_id,
                    Task.parent_task_id == None,  # noqa: E711
                    Task.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar() or 0
        wbs = str(cnt + 1)
        name = (act.get("name") or "").strip()[:255]
        # priority：1-5 整数，非法回退 3
        raw_pri = act.get("priority")
        try:
            pri = int(raw_pri)
        except (TypeError, ValueError):
            pri = 3
        if pri < 1 or pri > 5:
            pri = 3
        # status 白名单，非法回退 todo
        status = act.get("status")
        if status not in _VALID_STATUS:
            status = TaskStatus.TODO.value
        task = Task(
            project_id=project_id,
            wbs_code=wbs,
            name=name,
            description=act.get("description") or "",
            priority=pri,
            status=status,
            parent_task_id=act.get("parent_task_id"),
            planned_start=_parse_date(act.get("planned_start")),
            planned_end=_parse_date(act.get("planned_end")),
            labels=["ai-generated"],
            category="ai_action",
        )
        db.add(task)
        await db.flush()
        await db.refresh(task)
        return task


async def execute_actions(
    db: AsyncSession,
    *,
    user,
    project_id: str,
    client_token: str,
    actions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    client_token = (client_token or "").strip()
    # 幂等：同 client_token 已执行过则直接返回首次结果，不重复写库
    if client_token:
        existing = (
            await db.execute(
                select(AIActionLog).where(AIActionLog.client_token == client_token)
            )
        ).scalars().first()
        if existing is not None:
            logger.info("AI 操作幂等命中 client_token=%s", client_token)
            return {
                "client_token": client_token,
                "results": existing.results or [],
                "succeeded": existing.succeeded or 0,
                "failed": existing.failed or 0,
                "truncated": bool(existing.truncated),
                "idempotent": True,
            }

    # 批量上限 30
    truncated = False
    if actions and len(actions) > 30:
        actions = actions[:30]
        truncated = True

    results: List[Dict[str, Any]] = []
    succeeded = 0
    failed = 0
    created_task_ids: List[str] = []

    for act in (actions or []):
        if not isinstance(act, dict):
            results.append({"action_type": "unknown", "task_id": None, "status": "error", "error": "action 不是对象"})
            failed += 1
            continue
        action_type = act.get("action") or act.get("action_type")
        try:
            if action_type == "create_task":
                _validate_create(act)
                created = await _do_create_task(db, project_id, act)
                created_task_ids.append(created.id)
                results.append({
                    "action_type": "create_task",
                    "task_id": created.id,
                    "status": "ok",
                    "created_task_id": created.id,
                })
                succeeded += 1
            elif action_type == "update_task_status":
                target = act.get("task_ref") or act.get("task_id")
                new_status = act.get("status")
                if new_status is None or new_status not in _VALID_STATUS:
                    raise ValueError(
                        f"INVALID_STATUS: {new_status} 不在允许范围 {sorted(_VALID_STATUS)}"
                    )
                resolved: Optional[Task] = None
                old_values: Optional[Dict[str, Any]] = None
                async with db.begin_nested():
                    resolved = await _resolve_task(db, project_id, str(target) if target is not None else "")
                    if resolved is None:
                        raise ValueError("NOT_FOUND: 找不到目标任务")
                    if resolved.project_id != project_id:
                        raise ValueError("AUTH_DENIED: 任务不属于该项目")
                    old_values = {"status": resolved.status, "version": resolved.version}
                    resolved.status = new_status
                    resolved.version = (resolved.version or 1) + 1
                results.append({
                    "action_type": "update_task_status",
                    "task_id": resolved.id,
                    "status": "ok",
                    "old_values": old_values,
                })
                succeeded += 1
            else:
                raise ValueError(f"UNSUPPORTED_ACTION: 不支持的操作类型 {action_type}")
        except Exception as e:
            err = str(e)
            results.append({
                "action_type": str(action_type or "unknown"),
                "task_id": None,
                "status": "error",
                "error": err,
            })
            failed += 1

    # 整体状态：全成功=ok；部分成功=partial；全失败=error
    if failed == 0:
        overall_status = "ok"
    elif succeeded > 0:
        overall_status = "partial"
    else:
        overall_status = "error"

    # 一张卡片（client_token）一行日志：统一在外层事务落库（即便业务全失败也要留痕）
    log = AIActionLog(
        user_id=getattr(user, "id", None),
        project_id=project_id,
        client_token=client_token or uuid.uuid4().hex,
        action_count=len(results),
        results=results,
        created_task_ids=created_task_ids,
        status=overall_status,
        succeeded=succeeded,
        failed=failed,
        truncated=1 if truncated else 0,
    )
    db.add(log)
    try:
        await db.flush()
    except IntegrityError:
        # 并发重复确认兜底：另一请求已落库，回滚本会话（含可能重复的建库）并复用已有日志
        await db.rollback()
        existing = (
            await db.execute(
                select(AIActionLog).where(AIActionLog.client_token == client_token)
            )
        ).scalars().first()
        if existing is not None:
            logger.info("AI 操作幂等命中(并发兜底) client_token=%s", client_token)
            return {
                "client_token": client_token,
                "results": existing.results or [],
                "succeeded": existing.succeeded or 0,
                "failed": existing.failed or 0,
                "truncated": bool(existing.truncated),
                "idempotent": True,
            }
        raise

    return {
        "client_token": client_token,
        "results": results,
        "succeeded": succeeded,
        "failed": failed,
        "truncated": truncated,
        "idempotent": False,
    }


class AIActionService:
    async def execute_actions(self, db, *, user, project_id, client_token, actions):
        return await execute_actions(
            db, user=user, project_id=project_id, client_token=client_token, actions=actions
        )


ai_action_service = AIActionService()

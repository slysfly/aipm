"""
PMI中国AI项目管理社区 - 级联完成服务

产品规则（来自需求）：
1. 当 Sprint 内「所有」任务（按 task.sprint_id 一对一归属）都已关闭（done 或 cancelled）时，
   该 Sprint 自动标记为 completed。
2. 当项目内「所有」Sprint 都已 completed 时，项目自动标记为 completed。
3. 任务被移除（软删除）或异动到其他 Sprint / 项目后，不再计入原 Sprint / 项目统计
   —— 由 task.sprint_id / task.project_id 外键 + 统计查询排除 is_deleted 自然保证。

设计说明（派生式状态，双向推导）：
- 满足"全部完成"条件 → 置为 completed；
- 不再满足（如某任务被重开 / 移走 / 新增未完成任务）→ 若当前为 completed 则回退到 active；
- 无任务 / 无 Sprint 时保持现状，避免误判空容器为完成或误回退手动状态。

注意：cancelled 视为"已退出范围"，不阻塞 Sprint / 项目完成；这是项目管理常见实践。
如后续需要"仅 done 才算完成"，调整 TASK_CLOSED_STATUSES 即可。
"""
from datetime import datetime
from sqlalchemy import select, func

from app.models import Task, Sprint, Project

# 视为"已完成/已关闭"的任务状态
TASK_CLOSED_STATUSES = {"done", "cancelled"}

# 状态取值（与 Sprint.status / Project.status 取值保持一致）
SPRINT_COMPLETED = "completed"
SPRINT_REVERT = "active"
PROJECT_COMPLETED = "completed"
PROJECT_REVERT = "active"


async def recompute_sprint_completion(db, sprint_id: str) -> None:
    """依据 Sprint 内任务的关闭情况，推导 Sprint 状态。"""
    if not sprint_id:
        return

    total = await db.scalar(
        select(func.count(Task.id)).where(
            Task.sprint_id == sprint_id,
            Task.is_deleted == False,
        )
    )
    if not total:
        # 无任务：保持现状（不自动完成，也不回退），避免误判空 Sprint
        return

    closed = await db.scalar(
        select(func.count(Task.id)).where(
            Task.sprint_id == sprint_id,
            Task.is_deleted == False,
            Task.status.in_(TASK_CLOSED_STATUSES),
        )
    )

    sprint = await db.get(Sprint, sprint_id)
    if sprint is None:
        return

    if closed == total:
        if sprint.status != SPRINT_COMPLETED:
            sprint.status = SPRINT_COMPLETED
            sprint.updated_at = datetime.now()
    else:
        if sprint.status == SPRINT_COMPLETED:
            sprint.status = SPRINT_REVERT
            sprint.updated_at = datetime.now()


async def recompute_project_completion(db, project_id: str) -> None:
    """依据项目内所有 Sprint 的完成情况，推导项目状态。"""
    if not project_id:
        return

    total = await db.scalar(
        select(func.count(Sprint.id)).where(Sprint.project_id == project_id)
    )
    if not total:
        # 无 Sprint：保持现状，不基于 Sprint 推导
        return

    completed = await db.scalar(
        select(func.count(Sprint.id)).where(
            Sprint.project_id == project_id,
            Sprint.status == SPRINT_COMPLETED,
        )
    )

    project = await db.get(Project, project_id)
    if project is None:
        return

    if completed == total:
        if project.status != PROJECT_COMPLETED:
            project.status = PROJECT_COMPLETED
            project.updated_at = datetime.now()
    else:
        if project.status == PROJECT_COMPLETED:
            project.status = PROJECT_REVERT
            project.updated_at = datetime.now()


async def recompute_after_task_change(
    db,
    *,
    old_sprint_id: str = None,
    old_project_id: str = None,
    new_sprint_id: str = None,
    new_project_id: str = None,
) -> None:
    """任务变更（创建 / 更新 / 删除）后，重算涉及的 Sprint 与项目（去重）。

    顺序：先重算 Sprint，再重算 Project（Project 完成态依赖 Sprint 状态）。
    """
    sprint_ids = {s for s in (old_sprint_id, new_sprint_id) if s}
    project_ids = {p for p in (old_project_id, new_project_id) if p}

    # 先 Sprint（可能改变 Sprint.status），再 Project（读取最新 Sprint.status）
    for sid in sprint_ids:
        await recompute_sprint_completion(db, sid)
    # 关键：将 Sprint 状态变更落到 DB，否则后续 Project 重算读取不到最新状态
    await db.flush()
    for pid in project_ids:
        await recompute_project_completion(db, pid)
    await db.flush()

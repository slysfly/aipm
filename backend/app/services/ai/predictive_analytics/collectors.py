"""
数据收集模块
包含所有数据库查询逻辑：任务统计、项目速度、资源风险、范围蔓延检测
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import Task, Sprint, SprintTask, ResourceAllocation, Resource


async def get_task_stats(db: AsyncSession, project_id: str) -> Dict[str, Any]:
    """获取项目任务统计"""
    total_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id,
            Task.is_deleted == False
        )
    )
    total = total_result.scalar() or 0

    done_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id,
            Task.is_deleted == False,
            Task.status == "done"
        )
    )
    done = done_result.scalar() or 0

    in_progress_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id,
            Task.is_deleted == False,
            Task.status == "in_progress"
        )
    )
    in_progress = in_progress_result.scalar() or 0

    overdue_result = await db.execute(
        select(func.count(Task.id)).where(
            Task.project_id == project_id,
            Task.is_deleted == False,
            Task.planned_end < datetime.now(),
            Task.status != "done"
        )
    )
    overdue = overdue_result.scalar() or 0

    avg_progress_result = await db.execute(
        select(func.avg(Task.progress)).where(
            Task.project_id == project_id,
            Task.is_deleted == False
        )
    )
    avg_progress = avg_progress_result.scalar() or 0

    total_estimated_result = await db.execute(
        select(func.sum(Task.estimated_hours)).where(
            Task.project_id == project_id,
            Task.is_deleted == False
        )
    )
    total_estimated = total_estimated_result.scalar() or 0

    total_actual_result = await db.execute(
        select(func.sum(Task.actual_hours)).where(
            Task.project_id == project_id,
            Task.is_deleted == False
        )
    )
    total_actual = total_actual_result.scalar() or 0

    return {
        "total": total,
        "done": done,
        "in_progress": in_progress,
        "overdue": overdue,
        "completion_rate": round(done / total * 100, 1) if total > 0 else 0,
        "avg_progress": round(float(avg_progress), 1),
        "total_estimated_hours": round(float(total_estimated), 1),
        "total_actual_hours": round(float(total_actual), 1),
    }


async def calculate_velocity(db: AsyncSession, project_id: str) -> Dict[str, Any]:
    """计算项目历史速度"""
    done_result = await db.execute(
        select(Task).where(
            Task.project_id == project_id,
            Task.status == "done",
            Task.is_deleted == False,
            Task.actual_end != None
        ).order_by(Task.actual_end)
    )
    done_tasks = done_result.scalars().all()

    if len(done_tasks) < 3:
        return {
            "tasks_per_day": 0,
            "hours_per_day": 0,
            "sample_size": len(done_tasks),
            "reliable": False,
        }

    first_done = min(t.actual_end for t in done_tasks if t.actual_end)
    last_done = max(t.actual_end for t in done_tasks if t.actual_end)
    days_elapsed = max(1, (last_done - first_done).days)

    tasks_per_day = len(done_tasks) / days_elapsed
    total_hours = sum(float(t.actual_hours or t.estimated_hours or 0) for t in done_tasks)
    hours_per_day = total_hours / days_elapsed

    return {
        "tasks_per_day": round(tasks_per_day, 2),
        "hours_per_day": round(hours_per_day, 2),
        "sample_size": len(done_tasks),
        "reliable": len(done_tasks) >= 10,
    }


async def calculate_resource_risk(db: AsyncSession, project_id: str) -> Dict[str, Any]:
    """计算资源瓶颈风险"""
    allocations_result = await db.execute(
        select(ResourceAllocation).where(ResourceAllocation.project_id == project_id)
    )
    allocations = allocations_result.scalars().all()

    if not allocations:
        return {"score": 70, "level": "low", "description": "未记录资源分配数据"}

    person_load = defaultdict(float)
    for alloc in allocations:
        person_load[alloc.resource_id] += float(alloc.allocated_hours or 0)

    if not person_load:
        return {"score": 70, "level": "low", "description": "未记录资源分配数据"}

    resource_ids = list(person_load.keys())
    capacity_result = await db.execute(
        select(Resource).where(Resource.id.in_(resource_ids))
    )
    resources = capacity_result.scalars().all()
    capacity_map = {r.id: float(r.capacity or 8) for r in resources}

    overloaded = 0
    max_load_ratio = 0
    for rid, hours in person_load.items():
        capacity = capacity_map.get(rid, 8) * 5
        ratio = hours / capacity if capacity > 0 else 0
        max_load_ratio = max(max_load_ratio, ratio)
        if ratio > 1.2:
            overloaded += 1

    if max_load_ratio > 1.5:
        score = 30
        level = "critical"
        description = f"{overloaded}人严重超载，最高负载{max_load_ratio:.1f}倍"
    elif max_load_ratio > 1.2:
        score = 50
        level = "high"
        description = f"{overloaded}人超载，最高负载{max_load_ratio:.1f}倍"
    elif max_load_ratio > 1.0:
        score = 70
        level = "medium"
        description = f"部分人员接近满负荷，最高负载{max_load_ratio:.1f}倍"
    else:
        score = 90
        level = "low"
        description = f"资源负载正常，最高负载{max_load_ratio:.1f}倍"

    return {
        "score": score,
        "level": level,
        "description": description,
        "overloaded_count": overloaded,
        "max_load_ratio": round(max_load_ratio, 2),
    }


async def detect_scope_creep(db: AsyncSession, sprint_id: str, current_task_count: int) -> Dict[str, Any]:
    """检测范围蔓延"""
    sprint_result = await db.execute(
        select(Sprint).where(Sprint.id == sprint_id)
    )
    sprint = sprint_result.scalar_one_or_none()
    if not sprint or not sprint.start_date:
        return {"detected": False, "message": "无法检测", "severity": "low", "added_tasks": 0}

    cutoff_date = datetime.combine(sprint.start_date + timedelta(days=7), datetime.min.time())

    late_additions_result = await db.execute(
        select(func.count(SprintTask.id)).where(
            SprintTask.sprint_id == sprint_id,
            SprintTask.added_at > cutoff_date
        )
    )
    late_additions = late_additions_result.scalar() or 0

    if late_additions == 0:
        return {"detected": False, "message": "未检测到范围蔓延", "severity": "low", "added_tasks": 0}

    creep_ratio = late_additions / current_task_count if current_task_count > 0 else 0

    if creep_ratio > 0.3:
        severity = "high"
        message = f"严重范围蔓延，Sprint中{late_additions}个任务为后期添加({creep_ratio*100:.0f}%)"
    elif creep_ratio > 0.15:
        severity = "medium"
        message = f"范围蔓延警告，Sprint中{late_additions}个任务为后期添加({creep_ratio*100:.0f}%)"
    else:
        severity = "low"
        message = f"轻微范围蔓延，Sprint中{late_additions}个任务为后期添加({creep_ratio*100:.0f}%)"

    return {
        "detected": True,
        "message": message,
        "severity": severity,
        "added_tasks": late_additions,
        "creep_ratio": round(creep_ratio, 2),
    }

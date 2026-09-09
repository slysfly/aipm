"""任务数据收集"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from app.models import Task, TaskStatus, Project, Comment


class TaskCollector:
    """收集用户任务数据的收集器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_tasks_for_date(
        self,
        user_id: str,
        target_date: date
    ) -> Dict[str, Any]:
        """获取用户在指定日期的任务数据"""
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = datetime.combine(target_date + timedelta(days=1), datetime.min.time())

        result = await self.db.execute(
            select(Task, Project.name.label("project_name"))
            .join(Project, Task.project_id == Project.id)
            .where(
                and_(
                    Task.assignee_id == user_id,
                    Task.is_deleted == False,
                    or_(
                        and_(Task.actual_end >= start_dt, Task.actual_end < end_dt),
                        and_(Task.updated_at >= start_dt, Task.updated_at < end_dt),
                        Task.status == TaskStatus.IN_PROGRESS.value,
                    )
                )
            )
        )
        tasks = result.fetchall()

        completed = []
        in_progress = []
        for task_row in tasks:
            task = task_row[0]
            project_name = task_row[1]
            task_data = {
                "task_id": task.id,
                "title": task.name,
                "project_name": project_name,
                "description": task.description or "",
                "status": task.status,
                "progress": float(task.progress or 0),
            }
            if task.status == TaskStatus.DONE.value and task.actual_end and start_dt <= task.actual_end < end_dt:
                completed.append(task_data)
            elif task.status == TaskStatus.IN_PROGRESS.value:
                in_progress.append(task_data)

        result = await self.db.execute(
            select(func.sum(Task.actual_hours))
            .where(
                and_(
                    Task.assignee_id == user_id,
                    Task.is_deleted == False,
                    Task.updated_at >= start_dt,
                    Task.updated_at < end_dt,
                )
            )
        )
        total_hours = result.scalar() or 0

        return {
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "total_hours": float(total_hours) if total_hours else 0,
        }

    async def get_user_tasks_for_period(
        self,
        user_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """获取用户在指定时间段内的任务数据"""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())

        result = await self.db.execute(
            select(Task, Project.name.label("project_name"))
            .join(Project, Task.project_id == Project.id)
            .where(
                and_(
                    Task.assignee_id == user_id,
                    Task.is_deleted == False,
                    or_(
                        and_(Task.actual_end >= start_dt, Task.actual_end < end_dt),
                        and_(Task.updated_at >= start_dt, Task.updated_at < end_dt),
                        Task.status == TaskStatus.IN_PROGRESS.value,
                    )
                )
            )
        )
        tasks = result.fetchall()

        completed = []
        in_progress = []
        for task_row in tasks:
            task = task_row[0]
            project_name = task_row[1]
            task_data = {
                "task_id": task.id,
                "title": task.name,
                "project_name": project_name,
                "description": task.description or "",
                "status": task.status,
                "progress": float(task.progress or 0),
                "actual_hours": float(task.actual_hours or 0),
                "completed_at": task.actual_end.isoformat() if task.actual_end else None,
            }
            if task.status == TaskStatus.DONE.value and task.actual_end and start_dt <= task.actual_end < end_dt:
                completed.append(task_data)
            elif task.status == TaskStatus.IN_PROGRESS.value:
                in_progress.append(task_data)

        result = await self.db.execute(
            select(func.sum(Task.actual_hours))
            .where(
                and_(
                    Task.assignee_id == user_id,
                    Task.is_deleted == False,
                    Task.updated_at >= start_dt,
                    Task.updated_at < end_dt,
                )
            )
        )
        total_hours = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(Comment.id))
            .where(
                and_(
                    Comment.user_id == user_id,
                    Comment.is_deleted == False,
                    Comment.created_at >= start_dt,
                    Comment.created_at < end_dt,
                )
            )
        )
        comment_count = result.scalar() or 0

        project_ids = list(set(t[0].project_id for t in tasks))

        return {
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "total_hours": float(total_hours) if total_hours else 0,
            "comment_count": comment_count,
            "project_count": len(project_ids),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }

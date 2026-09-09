"""项目数据收集"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case

from app.models import Task, TaskStatus, Project, Risk, Milestone, User
from app.models.permission import ProjectMember


class ProjectCollector:
    """收集项目数据的收集器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_project_data(
        self,
        project_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """获取项目数据"""
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "项目不存在"}

        if not start_date:
            start_date = project.start_date or date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        result = await self.db.execute(
            select(
                func.count(Task.id).label("total"),
                func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)).label("completed"),
                func.sum(case((Task.status == TaskStatus.IN_PROGRESS.value, 1), else_=0)).label("in_progress"),
                func.avg(Task.progress).label("avg_progress"),
                func.sum(Task.actual_hours).label("total_hours"),
            )
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False,
                )
            )
        )
        task_stats = result.fetchone()

        result = await self.db.execute(
            select(Risk)
            .where(Risk.project_id == project_id)
        )
        risks = result.scalars().all()

        result = await self.db.execute(
            select(Milestone)
            .where(Milestone.project_id == project_id)
        )
        milestones = result.scalars().all()

        result = await self.db.execute(
            select(
                Task.assignee_id,
                User.username,
                func.count(Task.id).label("completed_count"),
                func.sum(Task.actual_hours).label("total_hours"),
            )
            .join(User, Task.assignee_id == User.id, isouter=True)
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False,
                    Task.assignee_id.isnot(None),
                )
            )
            .group_by(Task.assignee_id, User.username)
        )
        member_stats = result.fetchall()

        result = await self.db.execute(
            select(ProjectMember, User)
            .join(User, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
        )
        members = result.fetchall()

        total_tasks = task_stats.total or 0
        completed_tasks = task_stats.completed or 0
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        return {
            "project_id": project.id,
            "project_name": project.name,
            "project_description": project.description or "",
            "project_status": project.status,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "task_stats": {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "in_progress_tasks": task_stats.in_progress or 0,
                "completion_rate": round(completion_rate, 2),
                "avg_progress": round(float(task_stats.avg_progress or 0), 2),
                "total_hours": float(task_stats.total_hours or 0),
            },
            "risks": [
                {
                    "risk_id": r.id,
                    "name": r.name,
                    "category": r.category,
                    "probability": float(r.probability or 0),
                    "impact": float(r.impact or 0),
                    "risk_score": float(r.risk_score or 0),
                    "status": r.status,
                    "description": r.description or "",
                }
                for r in risks
            ],
            "milestones": [
                {
                    "milestone_id": m.id,
                    "name": m.name,
                    "due_date": m.due_date.isoformat() if m.due_date else None,
                    "status": m.status,
                    "description": m.description or "",
                }
                for m in milestones
            ],
            "team_contributions": [
                {
                    "user_id": m[0].assignee_id,
                    "user_name": m[1] or "未知用户",
                    "completed_tasks": m[2] or 0,
                    "total_hours": float(m[3] or 0),
                }
                for m in member_stats
            ],
            "team_size": len(members),
        }

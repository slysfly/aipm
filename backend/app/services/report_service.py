from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case, extract
from sqlalchemy.orm import selectinload

from app.models import Project, Task, TaskStatus, Risk, ResourceAllocation, EVMSnapshot, Comment, CostRecord
from app.models.permission import ProjectMember


class ReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_project_progress(
        self,
        project_id: str,
        period: str = "week"
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "项目不存在"}

        result = await self.db.execute(
            select(
                func.count(Task.id).label("total"),
                func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)).label("completed"),
                func.sum(case((Task.status == TaskStatus.IN_PROGRESS.value, 1), else_=0)).label("in_progress"),
                func.sum(case((Task.status == TaskStatus.TODO.value, 1), else_=0)).label("todo"),
                func.avg(Task.progress).label("avg_progress")
            )
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False
                )
            )
        )
        stats = result.fetchone()

        total = stats.total or 0
        completed = stats.completed or 0
        completion_rate = (completed / total * 100) if total > 0 else 0

        if period == "week":
            group_by = extract("week", Task.created_at)
            date_label = "week"
        else:
            group_by = extract("month", Task.created_at)
            date_label = "month"

        result = await self.db.execute(
            select(
                group_by.label("period"),
                func.count(Task.id).label("created"),
                func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)).label("completed")
            )
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False
                )
            )
            .group_by(group_by)
            .order_by(group_by)
        )
        trend = [
            {
                "period": str(row.period),
                "created": row.created,
                "completed": row.completed or 0,
                "completion_rate": round((row.completed or 0) / row.created * 100, 2) if row.created > 0 else 0
            }
            for row in result.fetchall()
        ]

        return {
            "project_id": project_id,
            "project_name": project.name,
            "period": period,
            "total_tasks": total,
            "completed_tasks": completed,
            "in_progress_tasks": stats.in_progress or 0,
            "todo_tasks": stats.todo or 0,
            "completion_rate": round(completion_rate, 2),
            "avg_progress": round(float(stats.avg_progress or 0), 2),
            "trend": trend
        }

    async def get_burndown_data(
        self,
        project_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "项目不存在"}

        if not start_date:
            start_date = project.start_date or date.today() - timedelta(days=30)
        if not end_date:
            end_date = project.end_date or date.today() + timedelta(days=30)

        result = await self.db.execute(
            select(func.count(Task.id))
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False
                )
            )
        )
        total_tasks = result.scalar() or 0

        result = await self.db.execute(
            select(
                func.date(Task.created_at).label("date"),
                func.count(Task.id).label("created"),
                func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)).label("completed")
            )
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False,
                    func.date(Task.created_at) >= start_date,
                    func.date(Task.created_at) <= end_date
                )
            )
            .group_by(func.date(Task.created_at))
            .order_by(func.date(Task.created_at))
        )
        daily_data = result.fetchall()

        current_date = start_date
        ideal_remaining = total_tasks
        actual_remaining = total_tasks
        data_points = []

        daily_map = {row.date: row for row in daily_data}
        days_count = (end_date - start_date).days or 1
        ideal_burn_rate = total_tasks / days_count

        while current_date <= end_date:
            day_data = daily_map.get(current_date)

            if day_data:
                actual_remaining -= (day_data.completed or 0)
                actual_remaining += (day_data.created or 0)

            ideal_remaining -= ideal_burn_rate
            ideal_remaining = max(0, ideal_remaining)
            actual_remaining = max(0, actual_remaining)

            data_points.append({
                "date": current_date.isoformat(),
                "ideal_remaining": round(ideal_remaining, 2),
                "actual_remaining": round(actual_remaining, 2),
                "created": day_data.created if day_data else 0,
                "completed": day_data.completed if day_data else 0
            })

            current_date += timedelta(days=1)

        return {
            "project_id": project_id,
            "project_name": project.name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_tasks": total_tasks,
            "data": data_points
        }

    async def get_velocity_data(
        self,
        project_id: str,
        sprint_length: int = 14
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "项目不存在"}

        result = await self.db.execute(
            select(
                Task.actual_end,
                Task.estimated_hours,
                Task.actual_hours
            )
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.status == TaskStatus.DONE.value,
                    Task.actual_end.isnot(None),
                    Task.is_deleted == False
                )
            )
        )
        rows = result.fetchall()

        # 按 ISO 周分组（数据库无关，避免 date_trunc 仅 PostgreSQL 支持的问题）
        from collections import defaultdict
        groups: Dict[Any, Dict[str, float]] = defaultdict(
            lambda: {"completed": 0, "estimated": 0.0, "actual": 0.0}
        )
        order = []
        for r in rows:
            d = r.actual_end
            if d is None:
                continue
            iso = d.isocalendar()  # (year, week, weekday)
            key = (iso[0], iso[1])
            if key not in groups:
                order.append(key)
            g = groups[key]
            g["completed"] += 1
            g["estimated"] += float(r.estimated_hours or 0)
            g["actual"] += float(r.actual_hours or 0)

        velocity_data = []
        total_completed = 0
        total_estimated = 0
        total_actual = 0

        for i, key in enumerate(order):
            g = groups[key]
            year, week = key
            monday = date.fromisocalendar(year, week, 1)
            total_completed += g["completed"]
            total_estimated += g["estimated"]
            total_actual += g["actual"]

            velocity_data.append({
                "sprint": i + 1,
                "start_date": monday.isoformat(),
                "completed_tasks": g["completed"],
                "estimated_hours": round(g["estimated"], 2),
                "actual_hours": round(g["actual"], 2),
                "velocity": round(g["completed"], 2)
            })

        week_count = len(order)
        avg_velocity = total_completed / week_count if week_count else 0
        avg_estimated = total_estimated / week_count if week_count else 0
        avg_actual = total_actual / week_count if week_count else 0

        return {
            "project_id": project_id,
            "project_name": project.name,
            "sprint_length": sprint_length,
            "total_sprints": week_count,
            "avg_velocity": round(avg_velocity, 2),
            "avg_estimated_hours": round(avg_estimated, 2),
            "avg_actual_hours": round(avg_actual, 2),
            "sprints": velocity_data
        }

    async def get_cumulative_flow(
        self,
        project_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
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

        statuses = [
            TaskStatus.BACKLOG.value,
            TaskStatus.TODO.value,
            TaskStatus.IN_PROGRESS.value,
            TaskStatus.IN_REVIEW.value,
            TaskStatus.TESTING.value,
            TaskStatus.DONE.value
        ]

        result = await self.db.execute(
            select(
                func.date(Task.created_at).label("date"),
                Task.status,
                func.count(Task.id).label("count")
            )
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False,
                    func.date(Task.created_at) >= start_date,
                    func.date(Task.created_at) <= end_date
                )
            )
            .group_by(func.date(Task.created_at), Task.status)
            .order_by(func.date(Task.created_at))
        )
        daily_status = result.fetchall()

        result = await self.db.execute(
            select(
                func.date(Task.updated_at).label("date"),
                Task.status,
                func.count(Task.id).label("count")
            )
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False,
                    func.date(Task.updated_at) >= start_date,
                    func.date(Task.updated_at) <= end_date
                )
            )
            .group_by(func.date(Task.updated_at), Task.status)
            .order_by(func.date(Task.updated_at))
        )
        daily_updates = result.fetchall()

        status_counts = {s: {} for s in statuses}
        for row in daily_status:
            d = row.date.isoformat() if hasattr(row.date, "isoformat") else str(row.date)
            if row.status in statuses:
                status_counts[row.status][d] = status_counts[row.status].get(d, 0) + row.count

        for row in daily_updates:
            d = row.date.isoformat() if hasattr(row.date, "isoformat") else str(row.date)
            if row.status in statuses:
                status_counts[row.status][d] = status_counts[row.status].get(d, 0) + row.count

        current_date = start_date
        data_points = []
        cumulative = {s: 0 for s in statuses}

        while current_date <= end_date:
            d = current_date.isoformat()
            for s in statuses:
                cumulative[s] += status_counts[s].get(d, 0)

            data_points.append({
                "date": d,
                **{s: cumulative[s] for s in statuses}
            })
            current_date += timedelta(days=1)

        return {
            "project_id": project_id,
            "project_name": project.name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "statuses": statuses,
            "data": data_points
        }

    async def get_evm_report(
        self,
        project_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "项目不存在"}

        if not start_date:
            start_date = project.start_date or date.today() - timedelta(days=90)
        if not end_date:
            end_date = date.today()

        result = await self.db.execute(
            select(EVMSnapshot)
            .where(
                and_(
                    EVMSnapshot.project_id == project_id,
                    EVMSnapshot.snapshot_date >= start_date,
                    EVMSnapshot.snapshot_date <= end_date
                )
            )
            .order_by(EVMSnapshot.snapshot_date)
        )
        snapshots = result.scalars().all()

        if not snapshots:
            result = await self.db.execute(
                select(
                    func.sum(Task.planned_value).label("pv"),
                    func.sum(Task.earned_value).label("ev"),
                    func.count(Task.id).label("total_tasks")
                )
                .where(
                    and_(
                        Task.project_id == project_id,
                        Task.is_deleted == False
                    )
                )
            )
            agg = result.fetchone()

            pv = float(agg.pv or 0)
            ev = float(agg.ev or 0)

            # AC 口径自洽：优先取真实成本记录(CostRecord)之和，
            # 与预算模块（budgets.py / budget_service.py）统一；无成本记录时回退任务 actual_cost
            cr_result = await self.db.execute(
                select(func.coalesce(func.sum(CostRecord.amount), 0))
                .where(CostRecord.project_id == project_id)
            )
            ac_from_records = float(cr_result.scalar() or 0)
            if ac_from_records > 0:
                ac = ac_from_records
            else:
                ac_result = await self.db.execute(
                    select(func.coalesce(func.sum(Task.actual_cost), 0))
                    .where(
                        and_(
                            Task.project_id == project_id,
                            Task.is_deleted == False
                        )
                    )
                )
                ac = float(ac_result.scalar() or 0)
            bac = float(project.budget or 0)

            cv = ev - ac
            sv = ev - pv
            cpi = ev / ac if ac > 0 else 1.0
            spi = ev / pv if pv > 0 else 1.0
            eac = bac / cpi if cpi > 0 else bac
            etc = eac - ac
            vac = bac - eac
            tcpi = (bac - ev) / (bac - ac) if (bac - ac) > 0 else 1.0

            return {
                "project_id": project_id,
                "project_name": project.name,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "current": {
                    "pv": round(pv, 2),
                    "ev": round(ev, 2),
                    "ac": round(ac, 2),
                    "bac": round(bac, 2),
                    "cv": round(cv, 2),
                    "sv": round(sv, 2),
                    "cpi": round(cpi, 4),
                    "spi": round(spi, 4),
                    "eac": round(eac, 2),
                    "etc": round(etc, 2),
                    "vac": round(vac, 2),
                    "tcpi": round(tcpi, 4)
                },
                "trend": []
            }

        trend = []
        for snap in snapshots:
            trend.append({
                "date": snap.snapshot_date.isoformat(),
                "pv": float(snap.planned_value or 0),
                "ev": float(snap.earned_value or 0),
                "ac": float(snap.actual_cost or 0),
                "cv": float(snap.cost_variance or 0),
                "sv": float(snap.schedule_variance or 0),
                "cpi": float(snap.cost_performance_index or 1.0),
                "spi": float(snap.schedule_performance_index or 1.0),
                "eac": float(snap.estimate_at_completion or 0),
                "etc": float(snap.estimate_to_complete or 0),
                "vac": float(snap.variance_at_completion or 0),
                "tcpi": float(snap.to_complete_performance_index or 1.0)
            })

        latest = snapshots[-1]
        bac = float(project.budget or 0)

        return {
            "project_id": project_id,
            "project_name": project.name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "current": {
                "pv": float(latest.planned_value or 0),
                "ev": float(latest.earned_value or 0),
                "ac": float(latest.actual_cost or 0),
                "bac": round(bac, 2),
                "cv": float(latest.cost_variance or 0),
                "sv": float(latest.schedule_variance or 0),
                "cpi": float(latest.cost_performance_index or 1.0),
                "spi": float(latest.schedule_performance_index or 1.0),
                "eac": float(latest.estimate_at_completion or 0),
                "etc": float(latest.estimate_to_complete or 0),
                "vac": float(latest.variance_at_completion or 0),
                "tcpi": float(latest.to_complete_performance_index or 1.0)
            },
            "trend": trend
        }

    async def get_resource_utilization(
        self,
        project_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "项目不存在"}

        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        result = await self.db.execute(
            select(
                ResourceAllocation.resource_id,
                func.sum(ResourceAllocation.allocated_hours).label("total_hours"),
                func.count(ResourceAllocation.id).label("allocation_count")
            )
            .where(
                and_(
                    ResourceAllocation.project_id == project_id,
                    ResourceAllocation.allocated_date >= start_date,
                    ResourceAllocation.allocated_date <= end_date
                )
            )
            .group_by(ResourceAllocation.resource_id)
        )
        allocations = result.fetchall()

        result = await self.db.execute(
            select(
                func.count(Task.id).label("total"),
                func.sum(Task.estimated_hours).label("estimated"),
                func.sum(Task.actual_hours).label("actual")
            )
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False,
                    Task.assignee_id.isnot(None)
                )
            )
        )
        task_stats = result.fetchone()

        total_days = (end_date - start_date).days or 1
        working_days = total_days * 5 / 7
        total_capacity = working_days * 8

        resource_data = []
        for alloc in allocations:
            utilization = (alloc.total_hours or 0) / total_capacity * 100 if total_capacity > 0 else 0
            resource_data.append({
                "resource_id": alloc.resource_id,
                "allocated_hours": float(alloc.total_hours or 0),
                "allocation_count": alloc.allocation_count,
                "utilization_rate": round(min(utilization, 100), 2)
            })

        avg_utilization = sum(r["utilization_rate"] for r in resource_data) / len(resource_data) if resource_data else 0

        return {
            "project_id": project_id,
            "project_name": project.name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_tasks_with_assignee": task_stats.total or 0,
            "total_estimated_hours": float(task_stats.estimated or 0),
            "total_actual_hours": float(task_stats.actual or 0),
            "avg_utilization_rate": round(avg_utilization, 2),
            "resources": resource_data
        }

    async def get_risk_trend(
        self,
        project_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "项目不存在"}

        if not start_date:
            start_date = project.start_date or date.today() - timedelta(days=90)
        if not end_date:
            end_date = date.today()

        result = await self.db.execute(
            select(
                Risk.status,
                func.count(Risk.id).label("count"),
                func.avg(Risk.risk_score).label("avg_score")
            )
            .where(Risk.project_id == project_id)
            .group_by(Risk.status)
        )
        status_distribution = [
            {
                "status": row.status,
                "count": row.count,
                "avg_score": round(float(row.avg_score or 0), 4)
            }
            for row in result.fetchall()
        ]

        result = await self.db.execute(
            select(
                Risk.category,
                func.count(Risk.id).label("count"),
                func.avg(Risk.risk_score).label("avg_score")
            )
            .where(Risk.project_id == project_id)
            .group_by(Risk.category)
        )
        category_distribution = [
            {
                "category": row.category,
                "count": row.count,
                "avg_score": round(float(row.avg_score or 0), 4)
            }
            for row in result.fetchall()
        ]

        result = await self.db.execute(
            select(
                func.date(Risk.created_at).label("date"),
                func.count(Risk.id).label("count"),
                func.avg(Risk.risk_score).label("avg_score")
            )
            .where(
                and_(
                    Risk.project_id == project_id,
                    func.date(Risk.created_at) >= start_date,
                    func.date(Risk.created_at) <= end_date
                )
            )
            .group_by(func.date(Risk.created_at))
            .order_by(func.date(Risk.created_at))
        )
        trend = [
            {
                "date": row.date.isoformat() if hasattr(row.date, "isoformat") else str(row.date),
                "count": row.count,
                "avg_score": round(float(row.avg_score or 0), 4)
            }
            for row in result.fetchall()
        ]

        return {
            "project_id": project_id,
            "project_name": project.name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "status_distribution": status_distribution,
            "category_distribution": category_distribution,
            "trend": trend
        }

    async def export_report(
        self,
        project_id: str,
        report_type: str,
        format_type: str = "csv",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Tuple[bytes, str]:
        if report_type == "project-progress":
            data = await self.get_project_progress(project_id)
        elif report_type == "burndown":
            data = await self.get_burndown_data(project_id, start_date, end_date)
        elif report_type == "velocity":
            data = await self.get_velocity_data(project_id)
        elif report_type == "cumulative-flow":
            data = await self.get_cumulative_flow(project_id, start_date, end_date)
        elif report_type == "evm":
            data = await self.get_evm_report(project_id, start_date, end_date)
        elif report_type == "resource-utilization":
            data = await self.get_resource_utilization(project_id, start_date, end_date)
        elif report_type == "risk-trend":
            data = await self.get_risk_trend(project_id, start_date, end_date)
        else:
            data = {"error": "未知报表类型"}

        if "error" in data:
            return b"", ""

        if format_type == "csv":
            return self._export_csv(data, report_type)
        elif format_type == "json":
            import json
            return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"
        else:
            return self._export_csv(data, report_type)

    def _export_csv(self, data: Dict[str, Any], report_type: str) -> Tuple[bytes, str]:
        # CSV 序列化逻辑已拆分至 app.services.report_exporters.build_report_csv
        from app.services.report_exporters import build_report_csv
        return build_report_csv(data, report_type)

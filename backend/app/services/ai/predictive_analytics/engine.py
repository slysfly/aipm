"""
AI预测分析引擎 - 主类
组合 collectors / models / analyzers / formatters 模块，保持原始 API 兼容
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import Project, Task, Sprint, SprintTask, Risk, ResourceAllocation, User
from app.models.risk import RiskAlert

from . import collectors
from . import models as prediction_models
from . import analyzers
from . import formatters


class PredictiveAnalytics:
    """AI预测分析引擎 - 纯统计方法实现"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ 项目健康度分析 ============

    async def analyze_project_health(self, project_id: str) -> Dict[str, Any]:
        """分析项目健康度"""
        result = await self.db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )
        project = result.scalar_one_or_none()
        if not project:
            return formatters.empty_health_response()

        task_stats = await collectors.get_task_stats(self.db, project_id)
        schedule_risk = analyzers.calculate_schedule_risk(project, task_stats)
        resource_risk = await collectors.calculate_resource_risk(self.db, project_id)
        budget_risk = analyzers.calculate_budget_risk(project)
        health_score = analyzers.compute_health_score(schedule_risk, resource_risk, budget_risk, task_stats)
        risk_level = analyzers.score_to_risk_level(health_score)

        risk_factors = []
        if schedule_risk["score"] < 60:
            risk_factors.append({
                "type": "schedule",
                "name": "延期风险",
                "severity": schedule_risk["level"],
                "description": schedule_risk["description"],
            })
        if resource_risk["score"] < 60:
            risk_factors.append({
                "type": "resource",
                "name": "资源瓶颈",
                "severity": resource_risk["level"],
                "description": resource_risk["description"],
            })
        if budget_risk["score"] < 60:
            risk_factors.append({
                "type": "budget",
                "name": "预算风险",
                "severity": budget_risk["level"],
                "description": budget_risk["description"],
            })

        recommendations = formatters.generate_recommendations(schedule_risk, resource_risk, budget_risk, task_stats)

        return {
            "project_id": project_id,
            "project_name": project.name,
            "health_score": round(health_score, 1),
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "recommendations": recommendations,
            "details": {
                "schedule_risk": schedule_risk,
                "resource_risk": resource_risk,
                "budget_risk": budget_risk,
                "task_stats": task_stats,
            },
            "analyzed_at": datetime.now().isoformat(),
        }

    # ============ 完成日期预测 ============

    async def predict_completion_date(self, project_id: str) -> Dict[str, Any]:
        """预测项目完成日期"""
        result = await self.db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )
        project = result.scalar_one_or_none()
        if not project:
            return formatters.empty_completion_response()

        task_stats = await collectors.get_task_stats(self.db, project_id)

        if task_stats["total"] == 0:
            return {
                "project_id": project_id,
                "predicted_date": project.end_date.isoformat() if project.end_date else None,
                "confidence_interval": None,
                "probability_ontime": None,
                "message": "项目暂无任务，无法预测",
            }

        velocity = await collectors.calculate_velocity(self.db, project_id)

        remaining_tasks = task_stats["total"] - task_stats["done"]
        remaining_hours = max(0, task_stats["total_estimated_hours"] - task_stats["total_actual_hours"])

        if velocity["tasks_per_day"] > 0:
            predicted_days = prediction_models.monte_carlo_simulation(
                remaining_tasks=remaining_tasks,
                remaining_hours=remaining_hours,
                velocity=velocity,
                simulations=1000
            )
        else:
            predicted_days = prediction_models.linear_prediction(remaining_tasks, task_stats)

        predicted_date = date.today() + timedelta(days=int(predicted_days["median"]))

        confidence_interval = {
            "optimistic": (date.today() + timedelta(days=int(predicted_days["p10"]))).isoformat(),
            "pessimistic": (date.today() + timedelta(days=int(predicted_days["p90"]))).isoformat(),
        }

        if project.end_date:
            days_to_deadline = (project.end_date - date.today()).days
            probability_ontime = prediction_models.calculate_ontime_probability(predicted_days, days_to_deadline)
        else:
            days_to_deadline = None
            probability_ontime = None

        return {
            "project_id": project_id,
            "project_name": project.name,
            "predicted_date": predicted_date.isoformat(),
            "confidence_interval": confidence_interval,
            "probability_ontime": round(probability_ontime, 2) if probability_ontime is not None else None,
            "planned_end_date": project.end_date.isoformat() if project.end_date else None,
            "days_to_deadline": days_to_deadline,
            "velocity": velocity,
            "remaining_tasks": remaining_tasks,
            "remaining_hours": remaining_hours,
            "simulation_stats": {
                "mean": round(predicted_days["mean"], 1),
                "median": round(predicted_days["median"], 1),
                "std_dev": round(predicted_days["std_dev"], 1),
            },
            "predicted_at": datetime.now().isoformat(),
        }

    # ============ Sprint风险分析 ============

    async def analyze_sprint_risk(self, sprint_id: str) -> Dict[str, Any]:
        """分析Sprint风险"""
        result = await self.db.execute(
            select(Sprint).where(Sprint.id == sprint_id)
        )
        sprint = result.scalar_one_or_none()
        if not sprint:
            return formatters.empty_sprint_risk_response()

        sprint_tasks_result = await self.db.execute(
            select(SprintTask).where(SprintTask.sprint_id == sprint_id)
        )
        sprint_tasks = sprint_tasks_result.scalars().all()

        task_ids = [st.task_id for st in sprint_tasks]
        if not task_ids:
            return {
                "sprint_id": sprint_id,
                "sprint_name": sprint.name,
                "on_track": True,
                "risk_factors": [],
                "suggested_actions": ["Sprint暂无任务"],
                "burndown_analysis": None,
                "scope_creep": None,
            }

        tasks_result = await self.db.execute(
            select(Task).where(Task.id.in_(task_ids), Task.is_deleted == False)
        )
        tasks = tasks_result.scalars().all()

        total = len(tasks)
        done = sum(1 for t in tasks if t.status == "done")
        in_progress = sum(1 for t in tasks if t.status == "in_progress")

        burndown = analyzers.analyze_burndown(sprint, done, total)
        scope_creep = await collectors.detect_scope_creep(self.db, sprint_id, total)

        on_track = burndown["on_track"] and not scope_creep["detected"]

        risk_factors = []
        if not burndown["on_track"]:
            risk_factors.append({
                "type": "burndown",
                "name": "燃尽趋势异常",
                "severity": "high" if burndown["completion_rate"] < 0.5 else "medium",
                "description": burndown["message"],
            })
        if scope_creep["detected"]:
            risk_factors.append({
                "type": "scope_creep",
                "name": "范围蔓延",
                "severity": scope_creep["severity"],
                "description": scope_creep["message"],
            })

        suggested_actions = []
        if not burndown["on_track"]:
            suggested_actions.append("加速任务完成，考虑将低优先级任务移出Sprint")
        if scope_creep["detected"]:
            suggested_actions.append("冻结Sprint范围，新需求放入待办列表")
        if done == 0 and total > 0:
            suggested_actions.append("Sprint尚未有任务完成，需要关注阻塞问题")
        if not risk_factors:
            suggested_actions.append("Sprint进展良好，继续保持")

        return {
            "sprint_id": sprint_id,
            "sprint_name": sprint.name,
            "on_track": on_track,
            "risk_factors": risk_factors,
            "suggested_actions": suggested_actions,
            "burndown_analysis": burndown,
            "scope_creep": scope_creep,
            "task_summary": {
                "total": total,
                "done": done,
                "in_progress": in_progress,
                "completion_rate": round(done / total, 2) if total > 0 else 0,
            },
            "analyzed_at": datetime.now().isoformat(),
        }

    # ============ 全局风险仪表盘 ============

    async def get_global_risk_dashboard(self) -> Dict[str, Any]:
        """获取全局风险仪表盘数据"""
        projects_result = await self.db.execute(
            select(Project).where(
                Project.is_deleted == False,
                Project.status.in_(["planning", "active", "paused"])
            )
        )
        projects = projects_result.scalars().all()

        project_healths = []
        high_risk_count = 0
        warning_count = 0
        healthy_count = 0
        total_alerts = 0

        for project in projects:
            health = await self.analyze_project_health(project.id)
            project_healths.append(health)

            if health["risk_level"] == "critical":
                high_risk_count += 1
            elif health["risk_level"] == "high":
                high_risk_count += 1
            elif health["risk_level"] == "medium":
                warning_count += 1
            else:
                healthy_count += 1

            total_alerts += len(health["risk_factors"])

        alerts_result = await self.db.execute(
            select(func.count(RiskAlert.id)).where(RiskAlert.status == "active")
        )
        active_alert_count = alerts_result.scalar() or 0

        return {
            "summary": {
                "total_projects": len(projects),
                "high_risk_projects": high_risk_count,
                "warning_projects": warning_count,
                "healthy_projects": healthy_count,
                "total_alerts": total_alerts,
                "active_risk_alerts": active_alert_count,
            },
            "projects": sorted(
                project_healths,
                key=lambda x: x["health_score"]
            ),
            "generated_at": datetime.now().isoformat(),
        }

    # ============ 保留的辅助方法（向后兼容） ============

    async def _get_task_stats(self, project_id: str) -> Dict[str, Any]:
        return await collectors.get_task_stats(self.db, project_id)

    async def _calculate_resource_risk(self, project_id: str) -> Dict[str, Any]:
        return await collectors.calculate_resource_risk(self.db, project_id)

    async def _calculate_velocity(self, project_id: str) -> Dict[str, Any]:
        return await collectors.calculate_velocity(self.db, project_id)

    async def _detect_scope_creep(self, sprint_id: str, current_task_count: int) -> Dict[str, Any]:
        return await collectors.detect_scope_creep(self.db, sprint_id, current_task_count)

    def _calculate_schedule_risk(self, project: Project, task_stats: Dict[str, Any]) -> Dict[str, Any]:
        return analyzers.calculate_schedule_risk(project, task_stats)

    def _calculate_budget_risk(self, project: Project) -> Dict[str, Any]:
        return analyzers.calculate_budget_risk(project)

    def _compute_health_score(self, schedule_risk, resource_risk, budget_risk, task_stats) -> float:
        return analyzers.compute_health_score(schedule_risk, resource_risk, budget_risk, task_stats)

    def _score_to_risk_level(self, score: float) -> str:
        return analyzers.score_to_risk_level(score)

    def _analyze_burndown(self, sprint, done_count: int, total_count: int) -> Dict[str, Any]:
        return analyzers.analyze_burndown(sprint, done_count, total_count)

    def _monte_carlo_simulation(self, remaining_tasks, remaining_hours, velocity, simulations=1000):
        return prediction_models.monte_carlo_simulation(remaining_tasks, remaining_hours, velocity, simulations)

    def _linear_prediction(self, remaining_tasks, task_stats):
        return prediction_models.linear_prediction(remaining_tasks, task_stats)

    def _calculate_ontime_probability(self, predicted_days, days_to_deadline):
        return prediction_models.calculate_ontime_probability(predicted_days, days_to_deadline)

    def _generate_recommendations(self, schedule_risk, resource_risk, budget_risk, task_stats):
        return formatters.generate_recommendations(schedule_risk, resource_risk, budget_risk, task_stats)

    def _empty_health_response(self):
        return formatters.empty_health_response()

    def _empty_completion_response(self):
        return formatters.empty_completion_response()

    def _empty_sprint_risk_response(self):
        return formatters.empty_sprint_risk_response()

"""
PMI中国AI项目管理社区 - AI预测分析引擎
基于纯统计方法的进度预测与风险预警系统

[CPMAI Phase: CPMAI Phase: Model Evaluation | Domain: Machine Learning — 预测分析模型]"""

import random
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models import Project, Task, Sprint, SprintTask, Risk, ResourceAllocation, User
from app.models.risk import RiskAlert


class PredictiveAnalytics:
    """AI预测分析引擎 - 纯统计方法实现"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ 项目健康度分析 ============

    async def analyze_project_health(self, project_id: str) -> Dict[str, Any]:
        """分析项目健康度"""
        # 获取项目信息
        result = await self.db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )
        project = result.scalar_one_or_none()
        if not project:
            return self._empty_health_response()

        # 获取项目任务统计
        task_stats = await self._get_task_stats(project_id)

        # 计算延期风险
        schedule_risk = self._calculate_schedule_risk(project, task_stats)

        # 计算资源瓶颈
        resource_risk = await self._calculate_resource_risk(project_id)

        # 计算预算风险
        budget_risk = self._calculate_budget_risk(project)

        # 综合健康度评分
        health_score = self._compute_health_score(schedule_risk, resource_risk, budget_risk, task_stats)

        # 风险等级
        risk_level = self._score_to_risk_level(health_score)

        # 风险因素汇总
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

        # AI建议措施
        recommendations = self._generate_recommendations(schedule_risk, resource_risk, budget_risk, task_stats)

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

    async def _get_task_stats(self, project_id: str) -> Dict[str, Any]:
        """获取项目任务统计"""
        total_result = await self.db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                Task.is_deleted == False
            )
        )
        total = total_result.scalar() or 0

        done_result = await self.db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                Task.is_deleted == False,
                Task.status == "done"
            )
        )
        done = done_result.scalar() or 0

        in_progress_result = await self.db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                Task.is_deleted == False,
                Task.status == "in_progress"
            )
        )
        in_progress = in_progress_result.scalar() or 0

        overdue_result = await self.db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id,
                Task.is_deleted == False,
                Task.planned_end < datetime.now(),
                Task.status != "done"
            )
        )
        overdue = overdue_result.scalar() or 0

        avg_progress_result = await self.db.execute(
            select(func.avg(Task.progress)).where(
                Task.project_id == project_id,
                Task.is_deleted == False
            )
        )
        avg_progress = avg_progress_result.scalar() or 0

        total_estimated_result = await self.db.execute(
            select(func.sum(Task.estimated_hours)).where(
                Task.project_id == project_id,
                Task.is_deleted == False
            )
        )
        total_estimated = total_estimated_result.scalar() or 0

        total_actual_result = await self.db.execute(
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

    def _calculate_schedule_risk(self, project: Project, task_stats: Dict[str, Any]) -> Dict[str, Any]:
        """计算延期风险"""
        if not project.end_date or not project.start_date:
            return {"score": 50, "level": "medium", "description": "未设置项目起止日期"}

        total_days = (project.end_date - project.start_date).days
        if total_days <= 0:
            return {"score": 50, "level": "medium", "description": "项目周期设置异常"}

        elapsed_days = (date.today() - project.start_date).days
        if elapsed_days < 0:
            elapsed_days = 0

        expected_progress = min(100, (elapsed_days / total_days) * 100) if total_days > 0 else 0
        actual_progress = task_stats["avg_progress"]

        progress_gap = expected_progress - actual_progress

        # 逾期任务影响
        overdue_penalty = min(30, task_stats["overdue"] * 5)

        if progress_gap > 20:
            score = max(0, 40 - overdue_penalty)
            level = "critical"
            description = f"进度严重滞后，预期{expected_progress:.0f}% vs 实际{actual_progress:.0f}%"
        elif progress_gap > 10:
            score = max(0, 60 - overdue_penalty)
            level = "high"
            description = f"进度滞后，预期{expected_progress:.0f}% vs 实际{actual_progress:.0f}%"
        elif progress_gap > 0:
            score = max(0, 75 - overdue_penalty)
            level = "medium"
            description = f"进度略有滞后，预期{expected_progress:.0f}% vs 实际{actual_progress:.0f}%"
        else:
            score = min(100, 90 - overdue_penalty)
            level = "low"
            description = f"进度正常，实际{actual_progress:.0f}%"

        return {
            "score": score,
            "level": level,
            "description": description,
            "expected_progress": round(expected_progress, 1),
            "actual_progress": actual_progress,
            "overdue_tasks": task_stats["overdue"],
        }

    async def _calculate_resource_risk(self, project_id: str) -> Dict[str, Any]:
        """计算资源瓶颈风险"""
        # 获取项目资源分配
        allocations_result = await self.db.execute(
            select(ResourceAllocation).where(ResourceAllocation.project_id == project_id)
        )
        allocations = allocations_result.scalars().all()

        if not allocations:
            return {"score": 70, "level": "low", "description": "未记录资源分配数据"}

        # 按人员统计负载
        person_load = defaultdict(float)
        for alloc in allocations:
            person_load[alloc.resource_id] += float(alloc.allocated_hours or 0)

        if not person_load:
            return {"score": 70, "level": "low", "description": "未记录资源分配数据"}

        # 获取人员容量
        resource_ids = list(person_load.keys())
        capacity_result = await self.db.execute(
            select(Resource).where(Resource.id.in_(resource_ids))
        )
        resources = capacity_result.scalars().all()
        capacity_map = {r.id: float(r.capacity or 8) for r in resources}

        # 计算超载人数
        overloaded = 0
        max_load_ratio = 0
        for rid, hours in person_load.items():
            capacity = capacity_map.get(rid, 8) * 5  # 周容量
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

    def _calculate_budget_risk(self, project: Project) -> Dict[str, Any]:
        """计算预算风险"""
        budget = float(project.budget or 0)
        actual_cost = float(project.actual_cost or 0)

        if budget <= 0:
            return {"score": 70, "level": "low", "description": "未设置预算"}

        burn_rate = actual_cost / budget if budget > 0 else 0

        # 计算时间进度
        if project.start_date and project.end_date:
            total_days = (project.end_date - project.start_date).days
            elapsed_days = (date.today() - project.start_date).days
            time_progress = elapsed_days / total_days if total_days > 0 else 0
        else:
            time_progress = 0.5

        # CPI 计算
        cpi = time_progress / burn_rate if burn_rate > 0 else 1.0

        if burn_rate > time_progress * 1.3:
            score = max(0, 40)
            level = "high"
            description = f"预算消耗过快，已用{burn_rate*100:.0f}% vs 时间进度{time_progress*100:.0f}%"
        elif burn_rate > time_progress * 1.1:
            score = 60
            level = "medium"
            description = f"预算消耗偏快，已用{burn_rate*100:.0f}% vs 时间进度{time_progress*100:.0f}%"
        elif burn_rate > time_progress:
            score = 75
            level = "low"
            description = f"预算消耗略快，已用{burn_rate*100:.0f}% vs 时间进度{time_progress*100:.0f}%"
        else:
            score = 90
            level = "low"
            description = f"预算控制良好，已用{burn_rate*100:.0f}% vs 时间进度{time_progress*100:.0f}%"

        return {
            "score": score,
            "level": level,
            "description": description,
            "budget": budget,
            "actual_cost": actual_cost,
            "burn_rate": round(burn_rate, 2),
            "cpi": round(cpi, 2),
        }

    def _compute_health_score(
        self,
        schedule_risk: Dict[str, Any],
        resource_risk: Dict[str, Any],
        budget_risk: Dict[str, Any],
        task_stats: Dict[str, Any]
    ) -> float:
        """计算综合健康度评分"""
        weights = {"schedule": 0.4, "resource": 0.3, "budget": 0.2, "completion": 0.1}

        completion_score = task_stats["completion_rate"]

        score = (
            schedule_risk["score"] * weights["schedule"] +
            resource_risk["score"] * weights["resource"] +
            budget_risk["score"] * weights["budget"] +
            completion_score * weights["completion"]
        )
        return min(100, max(0, score))

    def _score_to_risk_level(self, score: float) -> str:
        """评分转风险等级"""
        if score >= 80:
            return "low"
        elif score >= 60:
            return "medium"
        elif score >= 40:
            return "high"
        else:
            return "critical"

    def _generate_recommendations(
        self,
        schedule_risk: Dict[str, Any],
        resource_risk: Dict[str, Any],
        budget_risk: Dict[str, Any],
        task_stats: Dict[str, Any]
    ) -> List[str]:
        """生成AI建议措施"""
        recommendations = []

        if schedule_risk["score"] < 60:
            recommendations.append("优先处理逾期任务，重新评估关键路径")
            recommendations.append("考虑缩减范围或增加资源投入以追赶进度")
        elif schedule_risk["score"] < 80:
            recommendations.append("密切关注任务进度，提前识别潜在延期")

        if resource_risk["score"] < 60:
            recommendations.append("重新分配工作负载，避免个别人员过载")
            recommendations.append("考虑引入外部资源或调整任务优先级")

        if budget_risk["score"] < 60:
            recommendations.append("审查支出明细，识别成本超支原因")
            recommendations.append("考虑申请追加预算或优化资源使用")

        if task_stats["overdue"] > 0:
            recommendations.append(f"立即处理 {task_stats['overdue']} 个逾期任务")

        if not recommendations:
            recommendations.append("项目整体状况良好，继续保持当前节奏")
            recommendations.append("建议定期进行风险复盘，提前预防潜在问题")

        return recommendations

    # ============ 完成日期预测 ============

    async def predict_completion_date(self, project_id: str) -> Dict[str, Any]:
        """预测项目完成日期"""
        result = await self.db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )
        project = result.scalar_one_or_none()
        if not project:
            return self._empty_completion_response()

        task_stats = await self._get_task_stats(project_id)

        if task_stats["total"] == 0:
            return {
                "project_id": project_id,
                "predicted_date": project.end_date.isoformat() if project.end_date else None,
                "confidence_interval": None,
                "probability_ontime": None,
                "message": "项目暂无任务，无法预测",
            }

        # 计算历史速度（velocity）
        velocity = await self._calculate_velocity(project_id)

        # 剩余工作量（以故事点/任务数估算）
        remaining_tasks = task_stats["total"] - task_stats["done"]
        remaining_hours = max(0, task_stats["total_estimated_hours"] - task_stats["total_actual_hours"])

        # 使用蒙特卡洛模拟
        if velocity["tasks_per_day"] > 0:
            predicted_days = self._monte_carlo_simulation(
                remaining_tasks=remaining_tasks,
                remaining_hours=remaining_hours,
                velocity=velocity,
                simulations=1000
            )
        else:
            # 无历史数据，使用简单线性预测
            predicted_days = self._linear_prediction(remaining_tasks, task_stats)

        predicted_date = date.today() + timedelta(days=int(predicted_days["median"]))

        # 置信区间
        confidence_interval = {
            "optimistic": (date.today() + timedelta(days=int(predicted_days["p10"]))).isoformat(),
            "pessimistic": (date.today() + timedelta(days=int(predicted_days["p90"]))).isoformat(),
        }

        # 准时完成概率
        if project.end_date:
            days_to_deadline = (project.end_date - date.today()).days
            probability_ontime = self._calculate_ontime_probability(predicted_days, days_to_deadline)
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

    async def _calculate_velocity(self, project_id: str) -> Dict[str, Any]:
        """计算项目历史速度"""
        # 获取已完成任务
        done_result = await self.db.execute(
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

        # 计算完成速率
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

    def _monte_carlo_simulation(
        self,
        remaining_tasks: int,
        remaining_hours: float,
        velocity: Dict[str, Any],
        simulations: int = 1000
    ) -> Dict[str, float]:
        """蒙特卡洛模拟预测完成天数"""
        import math

        base_rate = velocity["tasks_per_day"]
        # 添加随机波动（假设速度服从正态分布，标准差为均值的30%）
        std_dev_rate = base_rate * 0.3

        results = []
        for _ in range(simulations):
            # 随机采样速度
            sampled_rate = random.gauss(base_rate, std_dev_rate)
            sampled_rate = max(0.01, sampled_rate)  # 确保正数

            days = remaining_tasks / sampled_rate
            results.append(days)

        results.sort()

        mean = sum(results) / len(results)
        median = results[len(results) // 2]
        variance = sum((x - mean) ** 2 for x in results) / len(results)
        std_dev = math.sqrt(variance)

        return {
            "mean": mean,
            "median": median,
            "std_dev": std_dev,
            "p10": results[int(simulations * 0.1)],
            "p90": results[int(simulations * 0.9)],
        }

    def _linear_prediction(self, remaining_tasks: int, task_stats: Dict[str, Any]) -> Dict[str, float]:
        """简单线性预测（无历史数据时）"""
        # 假设每天完成1个任务
        estimated_days = remaining_tasks * 2  # 保守估计
        return {
            "mean": estimated_days,
            "median": estimated_days,
            "std_dev": estimated_days * 0.3,
            "p10": estimated_days * 0.7,
            "p90": estimated_days * 1.3,
        }

    def _calculate_ontime_probability(self, predicted_days: Dict[str, float], days_to_deadline: int) -> float:
        """计算准时完成概率"""
        import math
        if days_to_deadline <= 0:
            return 0.0

        mean = predicted_days["mean"]
        std_dev = predicted_days["std_dev"]

        if std_dev == 0:
            return 1.0 if mean <= days_to_deadline else 0.0

        # 使用正态分布CDF计算概率
        z_score = (days_to_deadline - mean) / std_dev
        # 近似CDF
        probability = 0.5 * (1 + math.erf(z_score / math.sqrt(2)))
        return min(1.0, max(0.0, probability))

    # ============ Sprint风险分析 ============

    async def analyze_sprint_risk(self, sprint_id: str) -> Dict[str, Any]:
        """分析Sprint风险"""
        result = await self.db.execute(
            select(Sprint).where(Sprint.id == sprint_id)
        )
        sprint = result.scalar_one_or_none()
        if not sprint:
            return self._empty_sprint_risk_response()

        # 获取Sprint任务
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

        # 获取任务详情
        tasks_result = await self.db.execute(
            select(Task).where(Task.id.in_(task_ids), Task.is_deleted == False)
        )
        tasks = tasks_result.scalars().all()

        total = len(tasks)
        done = sum(1 for t in tasks if t.status == "done")
        in_progress = sum(1 for t in tasks if t.status == "in_progress")

        # 燃尽图趋势分析
        burndown = self._analyze_burndown(sprint, done, total)

        # Scope creep检测
        scope_creep = await self._detect_scope_creep(sprint_id, total)

        # 判断是否on track
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

        # 建议措施
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

    def _analyze_burndown(self, sprint: Sprint, done_count: int, total_count: int) -> Dict[str, Any]:
        """分析燃尽图趋势"""
        if not sprint.start_date or not sprint.end_date:
            return {"on_track": True, "message": "未设置Sprint日期", "completion_rate": 0}

        total_days = (sprint.end_date - sprint.start_date).days
        elapsed_days = (date.today() - sprint.start_date).days

        if total_days <= 0:
            return {"on_track": True, "message": "Sprint周期异常", "completion_rate": 0}

        if elapsed_days < 0:
            return {"on_track": True, "message": "Sprint尚未开始", "completion_rate": 0}

        time_progress = elapsed_days / total_days
        task_progress = done_count / total_count if total_count > 0 else 0

        # 理想情况下，任务进度应 >= 时间进度
        completion_rate = task_progress / time_progress if time_progress > 0 else 1.0

        if completion_rate < 0.5:
            on_track = False
            message = f"燃尽严重滞后，时间进度{time_progress*100:.0f}%但任务仅完成{task_progress*100:.0f}%"
        elif completion_rate < 0.8:
            on_track = False
            message = f"燃尽略滞后，时间进度{time_progress*100:.0f}%但任务仅完成{task_progress*100:.0f}%"
        else:
            on_track = True
            message = f"燃尽正常，任务完成进度{task_progress*100:.0f}% vs 时间进度{time_progress*100:.0f}%"

        return {
            "on_track": on_track,
            "message": message,
            "completion_rate": round(completion_rate, 2),
            "time_progress": round(time_progress, 2),
            "task_progress": round(task_progress, 2),
            "total_days": total_days,
            "elapsed_days": elapsed_days,
            "remaining_days": max(0, total_days - elapsed_days),
        }

    async def _detect_scope_creep(self, sprint_id: str, current_task_count: int) -> Dict[str, Any]:
        """检测范围蔓延"""
        # 获取Sprint初始任务数（Sprint开始后7天内添加的任务视为初始范围）
        sprint_result = await self.db.execute(
            select(Sprint).where(Sprint.id == sprint_id)
        )
        sprint = sprint_result.scalar_one_or_none()
        if not sprint or not sprint.start_date:
            return {"detected": False, "message": "无法检测", "severity": "low", "added_tasks": 0}

        # 统计Sprint开始7天后新增的任务
        cutoff_date = datetime.combine(sprint.start_date + timedelta(days=7), datetime.min.time())

        late_additions_result = await self.db.execute(
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

    # ============ 全局风险仪表盘 ============

    async def get_global_risk_dashboard(self) -> Dict[str, Any]:
        """获取全局风险仪表盘数据"""
        # 获取所有活跃项目
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

        # 获取活跃风险预警数量
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

    # ============ 辅助方法 ============

    def _empty_health_response(self) -> Dict[str, Any]:
        return {
            "project_id": None,
            "health_score": 0,
            "risk_level": "unknown",
            "risk_factors": [],
            "recommendations": ["项目不存在或已被删除"],
            "details": {},
        }

    def _empty_completion_response(self) -> Dict[str, Any]:
        return {
            "project_id": None,
            "predicted_date": None,
            "confidence_interval": None,
            "probability_ontime": None,
            "message": "项目不存在或已被删除",
        }

    def _empty_sprint_risk_response(self) -> Dict[str, Any]:
        return {
            "sprint_id": None,
            "on_track": False,
            "risk_factors": [{"type": "not_found", "name": "Sprint不存在", "severity": "high", "description": "指定的Sprint不存在"}],
            "suggested_actions": ["请检查Sprint ID是否正确"],
            "burndown_analysis": None,
            "scope_creep": None,
        }

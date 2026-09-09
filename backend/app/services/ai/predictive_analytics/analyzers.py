"""
分析逻辑模块
包含项目健康度分析函数：延期风险、预算风险、健康评分、燃尽分析
与数据库无关，为纯函数
"""

from datetime import date
from typing import Dict, Any

from app.models import Project


def calculate_schedule_risk(project: Project, task_stats: Dict[str, Any]) -> Dict[str, Any]:
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


def calculate_budget_risk(project: Project) -> Dict[str, Any]:
    """计算预算风险"""
    budget = float(project.budget or 0)
    actual_cost = float(project.actual_cost or 0)

    if budget <= 0:
        return {"score": 70, "level": "low", "description": "未设置预算"}

    burn_rate = actual_cost / budget if budget > 0 else 0

    if project.start_date and project.end_date:
        total_days = (project.end_date - project.start_date).days
        elapsed_days = (date.today() - project.start_date).days
        time_progress = elapsed_days / total_days if total_days > 0 else 0
    else:
        time_progress = 0.5

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


def compute_health_score(
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


def score_to_risk_level(score: float) -> str:
    """评分转风险等级"""
    if score >= 80:
        return "low"
    elif score >= 60:
        return "medium"
    elif score >= 40:
        return "high"
    else:
        return "critical"


def analyze_burndown(sprint, done_count: int, total_count: int) -> Dict[str, Any]:
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

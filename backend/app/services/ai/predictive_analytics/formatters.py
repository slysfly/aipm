"""
结果格式化模块
包含建议生成和空响应构造等格式化函数
"""

from typing import Dict, Any, List


def generate_recommendations(
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


def empty_health_response() -> Dict[str, Any]:
    return {
        "project_id": None,
        "health_score": 0,
        "risk_level": "unknown",
        "risk_factors": [],
        "recommendations": ["项目不存在或已被删除"],
        "details": {},
    }


def empty_completion_response() -> Dict[str, Any]:
    return {
        "project_id": None,
        "predicted_date": None,
        "confidence_interval": None,
        "probability_ontime": None,
        "message": "项目不存在或已被删除",
    }


def empty_sprint_risk_response() -> Dict[str, Any]:
    return {
        "sprint_id": None,
        "on_track": False,
        "risk_factors": [{"type": "not_found", "name": "Sprint不存在", "severity": "high", "description": "指定的Sprint不存在"}],
        "suggested_actions": ["请检查Sprint ID是否正确"],
        "burndown_analysis": None,
        "scope_creep": None,
    }

"""
预测模型模块
包含纯统计方法：蒙特卡洛模拟、线性预测、准时概率计算
与数据库无关，为纯函数
"""

import math
import random
from typing import Dict, Any


def monte_carlo_simulation(
    remaining_tasks: int,
    remaining_hours: float,
    velocity: Dict[str, Any],
    simulations: int = 1000
) -> Dict[str, float]:
    """蒙特卡洛模拟预测完成天数"""
    base_rate = velocity["tasks_per_day"]
    std_dev_rate = base_rate * 0.3

    results = []
    for _ in range(simulations):
        sampled_rate = random.gauss(base_rate, std_dev_rate)
        sampled_rate = max(0.01, sampled_rate)
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


def linear_prediction(remaining_tasks: int, task_stats: Dict[str, Any]) -> Dict[str, float]:
    """简单线性预测（无历史数据时）"""
    estimated_days = remaining_tasks * 2
    return {
        "mean": estimated_days,
        "median": estimated_days,
        "std_dev": estimated_days * 0.3,
        "p10": estimated_days * 0.7,
        "p90": estimated_days * 1.3,
    }


def calculate_ontime_probability(predicted_days: Dict[str, float], days_to_deadline: int) -> float:
    """计算准时完成概率"""
    if days_to_deadline <= 0:
        return 0.0

    mean = predicted_days["mean"]
    std_dev = predicted_days["std_dev"]

    if std_dev == 0:
        return 1.0 if mean <= days_to_deadline else 0.0

    z_score = (days_to_deadline - mean) / std_dev
    probability = 0.5 * (1 + math.erf(z_score / math.sqrt(2)))
    return min(1.0, max(0.0, probability))

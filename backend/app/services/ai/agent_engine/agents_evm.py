"""
EVM (Earned Value Management) Agent 模块
提供挣值管理相关的Agent逻辑
"""

from typing import Dict, Any, Optional


def calculate_evm_metrics(
    planned_value: float,
    earned_value: float,
    actual_cost: float,
    budget_at_completion: float,
) -> Dict[str, Any]:
    """计算EVM核心指标"""
    # 偏差分析
    sv = earned_value - planned_value  # 进度偏差
    cv = earned_value - actual_cost    # 成本偏差

    # 绩效指数
    spi = earned_value / planned_value if planned_value else 0.0
    cpi = earned_value / actual_cost if actual_cost else 0.0

    # 预测
    eac = budget_at_completion / cpi if cpi else 0.0  # 完工估算
    etc = eac - actual_cost                              # 完工尚需估算
    vac = budget_at_completion - eac                     # 完工偏差

    return {
        "planned_value": planned_value,
        "earned_value": earned_value,
        "actual_cost": actual_cost,
        "schedule_variance": round(sv, 2),
        "cost_variance": round(cv, 2),
        "spi": round(spi, 4),
        "cpi": round(cpi, 4),
        "estimate_at_completion": round(eac, 2),
        "estimate_to_complete": round(etc, 2),
        "variance_at_completion": round(vac, 2),
    }

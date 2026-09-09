"""
PMI中国AI项目管理社区 - 预算/成本跟踪 辅助函数
"""


def _to_float(value) -> float:
    return float(value) if value is not None else 0.0


def _calc_budget_response(budget, total_spent: float = 0) -> dict:
    total = _to_float(budget.total_budget)
    remaining = total - total_spent
    execution_rate = (total_spent / total * 100) if total > 0 else 0
    return {
        "total_spent": total_spent,
        "total_remaining": remaining,
        "execution_rate": round(execution_rate, 2),
        "is_over_budget": total_spent > total,
    }


def _calc_category_response(category) -> dict:
    allocated = _to_float(category.allocated_amount)
    spent = _to_float(category.spent_amount)
    remaining = allocated - spent
    execution_rate = (spent / allocated * 100) if allocated > 0 else 0
    return {
        "remaining": remaining,
        "execution_rate": round(execution_rate, 2),
        "is_over_budget": spent > allocated,
    }

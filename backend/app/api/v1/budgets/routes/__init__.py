"""
PMI中国AI项目管理社区 - 预算路由子包
"""

from app.api.v1.budgets.routes.budget import budget_router
from app.api.v1.budgets.routes.category import category_router
from app.api.v1.budgets.routes.cost_record import cost_record_router

__all__ = ["budget_router", "category_router", "cost_record_router"]

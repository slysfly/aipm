"""用户管理子系统 - 运营看板 API"""
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.ucm import Organization, Order, Refund, Transaction, UserLevel
from app.api.v1.ucm.deps import require_ucm_admin

router = APIRouter()


@router.get("/summary")
async def dashboard_summary(user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    # 组织统计
    res = await db.execute(select(func.count()).select_from(Organization).where(Organization.code != "DEFAULT"))
    org_total = res.scalar() or 0
    res = await db.execute(select(func.count()).select_from(Organization).where(Organization.status == "active", Organization.code != "DEFAULT"))
    org_active = res.scalar() or 0
    # 即将到期（30天内）
    soon = datetime.now() + timedelta(days=30)
    res = await db.execute(select(func.count()).select_from(Organization).where(Organization.expire_at < soon, Organization.expire_at > datetime.now(), Organization.code != "DEFAULT"))
    expiring = res.scalar() or 0
    # 收入（已付订单）
    res = await db.execute(select(func.coalesce(func.sum(Order.amount), 0)).where(Order.status == "paid"))
    revenue = float(res.scalar() or 0)
    # 退款
    res = await db.execute(select(func.coalesce(func.sum(Refund.amount), 0)).where(Refund.status == "done"))
    refund_total = float(res.scalar() or 0)
    # 待审退款
    res = await db.execute(select(func.count()).select_from(Refund).where(Refund.status == "pending"))
    refund_pending = res.scalar() or 0
    # 用户数
    res = await db.execute(select(func.count()).select_from(User))
    user_total = res.scalar() or 0

    return {
        "org_total": org_total, "org_active": org_active, "org_expiring": expiring,
        "revenue": revenue, "refund_total": refund_total, "refund_pending": refund_pending,
        "user_total": user_total,
    }

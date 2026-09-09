"""用户个人中心 API"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.ucm import Organization, UserOrganization, Order, Refund, Plan

router = APIRouter()

class ProfileUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    department: str | None = None
    position: str | None = None

class RechargeRequest(BaseModel):
    org_id: str
    plan_id: str
    billing_cycle: str = "monthly"
    payment_method: str = "manual_cash"
    remark: str | None = None

class RefundRequest(BaseModel):
    order_id: str
    amount: float
    reason: str
    method: str = "manual_refund"

@router.get("/me")
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取当前用户个人信息"""
    # 获取用户组织信息
    res = await db.execute(
        select(UserOrganization).where(UserOrganization.user_id == user.id)
    )
    memberships = res.scalars().all()
    
    org_info = []
    for m in memberships:
        res = await db.execute(select(Organization).where(Organization.id == m.org_id))
        org = res.scalar_one_or_none()
        if org:
            res = await db.execute(select(Plan).where(Plan.id == org.plan_id))
            plan = res.scalar_one_or_none()
            org_info.append({
                "org_id": org.id,
                "org_name": org.name,
                "plan_name": plan.name if plan else "未开通",
                "expire_at": org.expire_at.isoformat() if org.expire_at else None,
                "role_in_org": m.role_in_org,
            })
    
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "department": user.department,
        "position": user.position,
        "is_superuser": user.is_superuser,
        "is_org_admin": user.is_org_admin,
        "is_active": user.is_active,
        "level_code": user.level_code,
        "level_points": user.level_points,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "organizations": org_info,
    }

@router.put("/me")
async def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新个人信息"""
    for field in ["full_name", "phone", "department", "position"]:
        if field in payload and payload[field] is not None:
            setattr(user, field, payload[field])
    user.updated_at = datetime.now()
    await db.commit()
    await db.refresh(user)
    return {"message": "更新成功"}

@router.post("/recharge")
async def recharge(
    payload: RechargeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """用户申请充值"""
    # 检查用户属于该组织
    res = await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == user.id,
            UserOrganization.org_id == payload.org_id
        )
    )
    if not res.scalar_one_or_none():
        raise HTTPException(403, "您不属于该组织")
    
    # 检查套餐
    res = await db.execute(select(Plan).where(Plan.id == payload.plan_id))
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "套餐不存在")
    
    # 创建订单
    order = Order(
        org_id=payload.org_id,
        user_id=user.id,
        type="subscribe",
        plan_id=payload.plan_id,
        amount=plan.price_yearly if payload.billing_cycle == "yearly" else plan.price_monthly,
        currency="CNY",
        status="unpaid",
        payment_method=payload.payment_method,
        remark=payload.remark,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    
    return {
        "order_id": order.id,
        "amount": float(order.amount),
        "status": order.status,
        "message": "充值申请已提交，等待管理员确认",
    }

@router.get("/orders")
async def list_my_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户的订单列表"""
    res = await db.execute(
        select(UserOrganization.org_id).where(UserOrganization.user_id == user.id)
    )
    org_ids = [r.org_id for r in res.all()]
    
    if user.is_superuser:
        res = await db.execute(
            select(Order).order_by(Order.created_at.desc()).limit(50)
        )
    else:
        res = await db.execute(
            select(Order).where(Order.org_id.in_(org_ids)).order_by(Order.created_at.desc()).limit(50)
        )
    
    return [
        {
            "id": o.id,
            "org_id": o.org_id,
            "type": o.type,
            "amount": float(o.amount),
            "status": o.status,
            "payment_method": o.payment_method,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in res.scalars().all()
    ]

@router.post("/refund")
async def request_refund(
    payload: RefundRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """用户申请退费"""
    # 检查订单
    res = await db.execute(select(Order).where(Order.id == payload.order_id))
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "订单不存在")
    
    if order.status != "paid":
        raise HTTPException(400, "仅已支付订单可退款")
    
    # 检查用户是否属于该订单的组织
    res = await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == user.id,
            UserOrganization.org_id == order.org_id
        )
    )
    if not res.scalar_one_or_none() and not user.is_superuser:
        raise HTTPException(403, "无权对此订单申请退款")
    
    # 创建退款申请
    refund = Refund(
        order_id=order.id,
        org_id=order.org_id,
        amount=payload.amount,
        reason=payload.reason,
        method=payload.method,
        status="pending",
    )
    db.add(refund)
    await db.commit()
    await db.refresh(refund)
    
    return {
        "id": refund.id,
        "status": refund.status,
        "message": "退费申请已提交，等待管理员审批",
    }

@router.get("/refunds")
async def list_my_refunds(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户的退费申请列表"""
    res = await db.execute(
        select(UserOrganization.org_id).where(UserOrganization.user_id == user.id)
    )
    org_ids = [r.org_id for r in res.all()]
    
    if user.is_superuser:
        res = await db.execute(
            select(Refund).order_by(Refund.created_at.desc()).limit(50)
        )
    else:
        res = await db.execute(
            select(Refund).where(Refund.org_id.in_(org_ids)).order_by(Refund.created_at.desc()).limit(50)
        )
    
    return [
        {
            "id": r.id,
            "order_id": r.order_id,
            "amount": float(r.amount),
            "reason": r.reason,
            "method": r.method,
            "status": r.status,
            "handled_at": r.handled_at.isoformat() if r.handled_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in res.scalars().all()
    ]

# Admin 相关 API
@router.get("/users")
async def list_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin 查看所有用户"""
    if not current_user.is_superuser:
        raise HTTPException(403, "需要管理员权限")
    
    res = await db.execute(select(User).order_by(User.created_at.desc()).limit(100))
    users = res.scalars().all()
    
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "full_name": u.full_name,
            "is_superuser": u.is_superuser,
            "is_org_admin": u.is_org_admin,
            "is_active": u.is_active,
            "level_code": u.level_code,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in users
    ]

@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Admin 更新用户角色"""
    if not current_user.is_superuser:
        raise HTTPException(403, "需要管理员权限")
    
    res = await db.execute(select(User).where(User.id == user_id))
    target = res.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "用户不存在")
    
    if "is_superuser" in payload:
        target.is_superuser = payload["is_superuser"]
    if "is_org_admin" in payload:
        target.is_org_admin = payload["is_org_admin"]
    if "is_active" in payload:
        target.is_active = payload["is_active"]
    
    await db.commit()
    await db.refresh(target)
    return {"message": "用户角色已更新"}

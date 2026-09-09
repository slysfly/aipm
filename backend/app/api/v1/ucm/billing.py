"""用户管理子系统 - 收费 / 退费 / 资金流水 API"""
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.ucm import Organization, Plan, Order, OrderItem, Refund, Transaction
from app.api.v1.ucm.deps import require_ucm_admin, require_org_access

router = APIRouter()


def order_to_dict(o: Order) -> dict:
    return {"id": o.id, "org_id": o.org_id, "type": o.type, "plan_id": o.plan_id, "amount": float(o.amount),
            "currency": o.currency, "status": o.status, "payment_method": o.payment_method,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None, "invoice_no": o.invoice_no,
            "remark": o.remark, "created_at": o.created_at.isoformat() if o.created_at else None}


def refund_to_dict(r: Refund) -> dict:
    return {"id": r.id, "order_id": r.order_id, "org_id": r.org_id, "amount": float(r.amount),
            "reason": r.reason, "method": r.method, "status": r.status,
            "handled_at": r.handled_at.isoformat() if r.handled_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None}


# ── 订单（后台手动记账） ─────────────────────────────────────
@router.get("/orders")
async def list_orders(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), skip: int = 0, limit: int = 200):
    if user.is_superuser:
        res = await db.execute(select(Order).order_by(Order.created_at.desc()).offset(skip).limit(limit))
    else:
        res = await db.execute(select(UserOrganization.org_id).where(UserOrganization.user_id == user.id))
        org_ids = [r.org_id for r in res.all()]
        res = await db.execute(select(Order).where(Order.org_id.in_(org_ids)).order_by(Order.created_at.desc()))
    return [order_to_dict(o) for o in res.scalars().all()]


@router.post("/orders")
async def create_order(payload: dict, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(400, "org_id 必填")
    amount = Decimal(str(payload.get("amount", 0)))
    o = Order(org_id=org_id, user_id=user.id, type=payload.get("type", "subscribe"),
              plan_id=payload.get("plan_id"), amount=amount, currency=payload.get("currency", "CNY"),
              status="unpaid", payment_method=payload.get("payment_method"), remark=payload.get("remark"))
    db.add(o)
    await db.flush()
    for it in payload.get("items", []):
        db.add(OrderItem(order_id=o.id, item_type=it.get("item_type", "plan"),
                         ref_id=it.get("ref_id"), name=it.get("name", ""),
                         amount=Decimal(str(it.get("amount", 0))), quantity=it.get("quantity", 1)))
    await db.commit()
    await db.refresh(o)
    return order_to_dict(o)


@router.post("/orders/{order_id}/pay")
async def pay_order(order_id: str, payload: dict, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Order).where(Order.id == order_id))
    o = res.scalar_one_or_none()
    if not o:
        raise HTTPException(404, "订单不存在")
    if o.status == "paid":
        raise HTTPException(400, "订单已支付")
    o.status = "paid"
    o.payment_method = payload.get("payment_method", o.payment_method)
    o.paid_at = datetime.now()
    o.invoice_no = payload.get("invoice_no", o.invoice_no)
    # 资金流水
    res = await db.execute(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.org_id == o.org_id, Transaction.type == "income"))
    income = Decimal(res.scalar() or 0)
    res = await db.execute(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.org_id == o.org_id, Transaction.type == "refund"))
    refund = Decimal(res.scalar() or 0)
    balance = income - refund + o.amount
    db.add(Transaction(org_id=o.org_id, type="income", ref_id=o.id, amount=o.amount, balance_after=balance, operator=user.id))
    # 购买/续费套餐 -> 更新组织套餐与到期
    if o.plan_id and o.type in ("subscribe", "renew", "upgrade"):
        res = await db.execute(select(Plan).where(Plan.id == o.plan_id))
        plan = res.scalar_one_or_none()
        if plan:
            res = await db.execute(select(Organization).where(Organization.id == o.org_id))
            org = res.scalar_one_or_none()
            if org:
                org.plan_id = plan.id
                org.max_seats = plan.max_seats
                months = 12 if (payload.get("period") == "yearly" or o.type == "renew") else 1
                base = org.expire_at or datetime.now()
                from datetime import timedelta
                org.expire_at = base + timedelta(days=30 * months)
                org.status = "active"
    await db.commit()
    await db.refresh(o)
    return order_to_dict(o)


# ── 退款 ─────────────────────────────────────────────────────
@router.get("/refunds")
async def list_refunds(user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Refund).order_by(Refund.created_at.desc()))
    return [refund_to_dict(r) for r in res.scalars().all()]


@router.post("/refunds")
async def create_refund(payload: dict, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    order_id = payload.get("order_id")
    if not order_id:
        raise HTTPException(400, "order_id 必填")
    res = await db.execute(select(Order).where(Order.id == order_id))
    o = res.scalar_one_or_none()
    if not o:
        raise HTTPException(404, "订单不存在")
    if o.status != "paid":
        raise HTTPException(400, "仅已支付订单可退款")
    amount = Decimal(str(payload.get("amount", float(o.amount))))
    r = Refund(order_id=order_id, org_id=o.org_id, amount=amount, reason=payload.get("reason"),
               method=payload.get("method"), status="pending")
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return refund_to_dict(r)


@router.post("/refunds/{refund_id}/approve")
async def approve_refund(refund_id: str, user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Refund).where(Refund.id == refund_id))
    r = res.scalar_one_or_none()
    if not r:
        raise HTTPException(404, "退款不存在")
    if r.status != "pending":
        raise HTTPException(400, "退款已处理")
    r.status = "done"
    r.handled_by = user.id
    r.handled_at = datetime.now()
    # 关联交易 + 订单状态
    res = await db.execute(select(Order).where(Order.id == r.order_id))
    o = res.scalar_one_or_none()
    if o:
        o.status = "refunded"
    res = await db.execute(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.org_id == r.org_id, Transaction.type == "income"))
    income = Decimal(res.scalar() or 0)
    res = await db.execute(select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.org_id == r.org_id, Transaction.type == "refund"))
    refund = Decimal(res.scalar() or 0)
    balance = income - refund - r.amount
    db.add(Transaction(org_id=r.org_id, type="refund", ref_id=r.id, amount=r.amount, balance_after=balance, operator=user.id))
    await db.commit()
    await db.refresh(r)
    return refund_to_dict(r)


@router.post("/refunds/{refund_id}/reject")
async def reject_refund(refund_id: str, user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Refund).where(Refund.id == refund_id))
    r = res.scalar_one_or_none()
    if not r:
        raise HTTPException(404, "退款不存在")
    r.status = "rejected"
    r.handled_by = user.id
    r.handled_at = datetime.now()
    await db.commit()
    await db.refresh(r)
    return refund_to_dict(r)


# ── 资金流水 ─────────────────────────────────────────────────
@router.get("/transactions")
async def list_transactions(user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db), skip: int = 0, limit: int = 200):
    res = await db.execute(select(Transaction).order_by(Transaction.created_at.desc()).offset(skip).limit(limit))
    out = []
    for t in res.scalars().all():
        out.append({"id": t.id, "org_id": t.org_id, "type": t.type, "ref_id": t.ref_id,
                    "amount": float(t.amount), "balance_after": float(t.balance_after),
                    "created_at": t.created_at.isoformat() if t.created_at else None})
    return out

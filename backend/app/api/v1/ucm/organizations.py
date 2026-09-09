"""用户管理子系统 - 组织 / 部门 / 成员 API"""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.ucm import (
    Organization, Department, UserOrganization, Plan,
    Feature, Order, OrderItem,
)
from app.api.v1.ucm.deps import require_ucm_admin, require_org_access

router = APIRouter()


def _aware(dt):
    """DB 读出的 datetime 是 naive(UTC)，统一补 tzinfo 以便和 aware 比较"""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def org_to_dict(o: Organization) -> dict:
    return {
        "id": o.id, "name": o.name, "code": o.code, "parent_id": o.parent_id,
        "level": o.level, "owner_user_id": o.owner_user_id, "plan_id": o.plan_id,
        "status": o.status, "max_seats": o.max_seats, "used_seats": o.used_seats,
        "expire_at": o.expire_at.isoformat() if o.expire_at else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def dept_to_dict(d: Department) -> dict:
    return {"id": d.id, "org_id": d.org_id, "name": d.name, "parent_id": d.parent_id, "leader_user_id": d.leader_user_id}


# ── 组织 CRUD ────────────────────────────────────────────────
@router.get("/organizations")
async def list_organizations(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), skip: int = 0, limit: int = 200):
    if user.is_superuser:
        res = await db.execute(select(Organization).offset(skip).limit(limit))
    else:
        res = await db.execute(select(UserOrganization).where(UserOrganization.user_id == user.id))
        org_ids = [r.org_id for r in res.scalars().all()]
        res = await db.execute(select(Organization).where(Organization.id.in_(org_ids)))
    items = res.scalars().all()
    plan_ids = {o.plan_id for o in items if o.plan_id}
    plan_map: dict = {}
    if plan_ids:
        r = await db.execute(select(Plan).where(Plan.id.in_(plan_ids)))
        for p in r.scalars().all():
            plan_map[p.id] = p.name
    out = []
    for o in items:
        d = org_to_dict(o)
        d["plan_name"] = plan_map.get(o.plan_id)
        out.append(d)
    return {"items": out, "total": len(items)}


@router.get("/organizations/tree")
async def org_tree(user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Organization))
    orgs = res.scalars().all()
    # 批量取出套餐名（避免 N+1）
    plan_ids = {o.plan_id for o in orgs if o.plan_id}
    plan_map: dict = {}
    if plan_ids:
        r = await db.execute(select(Plan).where(Plan.id.in_(plan_ids)))
        for p in r.scalars().all():
            plan_map[p.id] = p.name
    by_id = {o.id: org_to_dict(o) for o in orgs}
    for o in orgs:
        node = by_id[o.id]
        node["plan_name"] = plan_map.get(o.plan_id)
        node["children"] = []
    roots = []
    for o in orgs:
        node = by_id[o.id]
        if o.parent_id and o.parent_id in by_id:
            by_id[o.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


@router.post("/organizations")
async def create_organization(payload: dict, user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    code = payload.get("code")
    if not code or not payload.get("name"):
        raise HTTPException(400, "code 和 name 必填")
    res = await db.execute(select(Organization).where(Organization.code == code))
    if res.scalar_one_or_none():
        raise HTTPException(400, "组织编码已存在")
    parent_id = payload.get("parent_id")
    level = 0
    if parent_id:
        res = await db.execute(select(Organization).where(Organization.id == parent_id))
        p = res.scalar_one_or_none()
        if not p:
            raise HTTPException(404, "父组织不存在")
        level = p.level + 1
    org = Organization(
        name=payload["name"], code=code, parent_id=parent_id, level=level,
        owner_user_id=payload.get("owner_user_id"), plan_id=payload.get("plan_id"),
        status=payload.get("status", "active"), max_seats=payload.get("max_seats", 5),
    )
    db.add(org)
    await db.flush()
    if org.owner_user_id:
        db.add(UserOrganization(user_id=org.owner_user_id, org_id=org.id, role_in_org="org_admin"))
        await db.execute(text("UPDATE users SET is_org_admin = 1, organization_id = :oid WHERE id = :uid"),
                         {"oid": org.id, "uid": org.owner_user_id})
    await db.commit()
    await db.refresh(org)
    return org_to_dict(org)


@router.get("/organizations/{org_id}")
async def get_organization(org_id: str, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Organization).where(Organization.id == org_id))
    o = res.scalar_one_or_none()
    if not o:
        raise HTTPException(404, "组织不存在")
    return org_to_dict(o)


@router.put("/organizations/{org_id}")
async def update_organization(org_id: str, payload: dict, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Organization).where(Organization.id == org_id))
    o = res.scalar_one_or_none()
    if not o:
        raise HTTPException(404, "组织不存在")
    for k in ["name", "status", "max_seats", "plan_id", "expire_at", "owner_user_id"]:
        if k in payload and payload[k] is not None:
            setattr(o, k, payload[k])
    await db.commit()
    await db.refresh(o)
    return org_to_dict(o)


@router.delete("/organizations/{org_id}")
async def delete_organization(org_id: str, user: User = Depends(require_ucm_admin), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Organization).where(Organization.id == org_id))
    o = res.scalar_one_or_none()
    if not o:
        raise HTTPException(404, "组织不存在")
    if o.code == "DEFAULT":
        raise HTTPException(400, "默认组织不可删除")
    await db.execute(text("DELETE FROM user_organizations WHERE org_id = :oid"), {"oid": org_id})
    await db.delete(o)
    await db.commit()
    return {"deleted": org_id}


# ── 部门 ─────────────────────────────────────────────────────
@router.get("/organizations/{org_id}/departments")
async def list_departments(org_id: str, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Department).where(Department.org_id == org_id))
    return [dept_to_dict(d) for d in res.scalars().all()]


@router.post("/organizations/{org_id}/departments")
async def create_department(org_id: str, payload: dict, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    if not payload.get("name"):
        raise HTTPException(400, "name 必填")
    d = Department(org_id=org_id, name=payload["name"], parent_id=payload.get("parent_id"), leader_user_id=payload.get("leader_user_id"))
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return dept_to_dict(d)


@router.delete("/organizations/{org_id}/departments/{dept_id}")
async def delete_department(org_id: str, dept_id: str, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Department).where(Department.id == dept_id, Department.org_id == org_id))
    d = res.scalar_one_or_none()
    if not d:
        raise HTTPException(404, "部门不存在")
    await db.delete(d)
    await db.commit()
    return {"deleted": dept_id}


# ── 成员 ─────────────────────────────────────────────────────
@router.get("/organizations/{org_id}/members")
async def list_members(org_id: str, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(UserOrganization, User.username, User.full_name, User.email, User.level_code)
        .join(User, User.id == UserOrganization.user_id)
        .where(UserOrganization.org_id == org_id)
    )
    rows = res.all()
    # 套餐信息（org 级别）
    org_res = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_res.scalar_one_or_none()
    plan_name = None
    plan_code = None
    org_expire_at = None
    if org and org.plan_id:
        plan_res = await db.execute(select(Plan).where(Plan.id == org.plan_id))
        plan = plan_res.scalar_one_or_none()
        if plan:
            plan_name = plan.name
            plan_code = plan.code
        org_expire_at = org.expire_at.isoformat() if org.expire_at else None
    now = datetime.now(timezone.utc)
    org_expire_aware = _aware(org.expire_at) if org else None
    is_default = (not org) or (not org.plan_id) or (org_expire_aware is not None and org_expire_aware < now)
    out = []
    for uo, username, full_name, email, level_code in rows:
        out.append({
            "user_id": uo.user_id, "department_id": uo.department_id,
            "role_in_org": uo.role_in_org, "username": username,
            "full_name": full_name, "email": email, "level_code": level_code,
            # 套餐信息：组织级（成员共享）
            "plan_id": org.plan_id if org else None,
            "plan_name": plan_name,
            "plan_code": plan_code,
            "expire_at": org_expire_at,
            "is_default_user": is_default,  # 组织无套餐/已过期 → 全部成员视为默认用户
        })
    return out


@router.post("/organizations/{org_id}/members")
async def add_member(org_id: str, payload: dict, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(400, "user_id 必填")
    # 席位硬限制
    res = await db.execute(select(Organization).where(Organization.id == org_id))
    org = res.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "组织不存在")
    res = await db.execute(select(func.count()).select_from(UserOrganization).where(UserOrganization.org_id == org_id))
    used = res.scalar() or 0
    if used >= org.max_seats:
        raise HTTPException(400, f"席位已满（{org.max_seats}），请升级套餐或增购席位")
    res = await db.execute(select(UserOrganization).where(UserOrganization.user_id == user_id, UserOrganization.org_id == org_id))
    if res.scalar_one_or_none():
        raise HTTPException(400, "该用户已在组织中")
    role = payload.get("role_in_org", "member")
    uo = UserOrganization(user_id=user_id, org_id=org_id, department_id=payload.get("department_id"), role_in_org=role)
    db.add(uo)

    # ── 套餐选择（可选）：为组织开通/续期套餐 ──
    plan_id = payload.get("plan_id")
    billing_cycle = payload.get("billing_cycle") or "monthly"  # monthly/yearly
    order_info = None
    if plan_id:
        plan_res = await db.execute(select(Plan).where(Plan.id == plan_id, Plan.is_active == True))
        plan = plan_res.scalar_one_or_none()
        if not plan:
            raise HTTPException(400, "套餐不存在或已停用")
        amount = plan.price_yearly if billing_cycle == "yearly" else plan.price_monthly
        amount = amount or 0
        # 创建订单（后台记账，立即 paid）
        order = Order(
            org_id=org_id, user_id=user.id, type="subscribe",
            plan_id=plan.id, amount=amount, currency="CNY",
            status="paid", payment_method="manual_cash",
            paid_at=datetime.now(timezone.utc),
            remark=f"添加成员时开通套餐({billing_cycle})",
        )
        db.add(order)
        await db.flush()
        db.add(OrderItem(
            order_id=order.id, item_type="plan", ref_id=plan.id,
            name=f"{plan.name}({'年付' if billing_cycle == 'yearly' else '月付'})",
            amount=amount, quantity=1,
        ))
        # 写入流水（收入）
        from app.models.ucm import Transaction
        db.add(Transaction(
            org_id=org_id, type="income", ref_id=order.id,
            amount=amount, balance_after=0, operator=user.id,
        ))
        # 更新组织套餐 + 到期时间（在已有到期基础上顺延，否则从今天起算）
        now = datetime.now(timezone.utc)
        base = _aware(org.expire_at) or now
        if base < now:
            base = now
        delta = timedelta(days=365 if billing_cycle == "yearly" else 30)
        org.plan_id = plan.id
        org.expire_at = base + delta
        order_info = {"order_id": order.id, "amount": float(amount), "expire_at": org.expire_at.isoformat()}

    if role == "org_admin":
        await db.execute(text("UPDATE users SET is_org_admin = 1, organization_id = :oid WHERE id = :uid"), {"oid": org_id, "uid": user_id})
    await db.execute(text("UPDATE organizations SET used_seats = (SELECT COUNT(*) FROM user_organizations WHERE org_id = :oid) WHERE id = :oid"), {"oid": org_id})
    await db.commit()
    return {
        "user_id": user_id, "org_id": org_id, "role_in_org": role,
        "plan_id": plan_id, "order": order_info,
        "is_default_user": plan_id is None,
    }


# ── 组织充值（默认用户 → 开通套餐） ───────────────────────────
@router.post("/organizations/{org_id}/recharge")
async def recharge_org(org_id: str, payload: dict, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    """为组织开通/续期套餐：
    - plan_id 必填
    - billing_cycle: monthly/yearly（默认 monthly）
    - payment_method: manual_wechat/manual_alipay/manual_bank/manual_cash（默认 manual_cash）
    - remark: 可选备注
    """
    plan_id = payload.get("plan_id")
    if not plan_id:
        raise HTTPException(400, "plan_id 必填")
    plan_res = await db.execute(select(Plan).where(Plan.id == plan_id, Plan.is_active == True))
    plan = plan_res.scalar_one_or_none()
    if not plan:
        raise HTTPException(400, "套餐不存在或已停用")
    org_res = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_res.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "组织不存在")
    billing_cycle = payload.get("billing_cycle") or "monthly"
    payment_method = payload.get("payment_method") or "manual_cash"
    amount = plan.price_yearly if billing_cycle == "yearly" else plan.price_monthly
    amount = amount or 0
    order = Order(
        org_id=org_id, user_id=user.id, type="subscribe",
        plan_id=plan.id, amount=amount, currency="CNY",
        status="paid", payment_method=payment_method,
        paid_at=datetime.now(timezone.utc),
        remark=payload.get("remark") or f"充值套餐({billing_cycle})",
    )
    db.add(order)
    await db.flush()
    db.add(OrderItem(
        order_id=order.id, item_type="plan", ref_id=plan.id,
        name=f"{plan.name}({'年付' if billing_cycle == 'yearly' else '月付'})",
        amount=amount, quantity=1,
    ))
    from app.models.ucm import Transaction
    db.add(Transaction(
        org_id=org_id, type="income", ref_id=order.id,
        amount=amount, balance_after=0, operator=user.id,
    ))
    now = datetime.now(timezone.utc)
    base = _aware(org.expire_at) or now
    if base < now:
        base = now
    delta = timedelta(days=365 if billing_cycle == "yearly" else 30)
    org.plan_id = plan.id
    org.expire_at = base + delta
    await db.commit()
    await db.refresh(order)
    return {
        "order_id": order.id, "plan_id": plan.id, "plan_name": plan.name,
        "amount": float(amount), "billing_cycle": billing_cycle,
        "expire_at": org.expire_at.isoformat(), "status": order.status,
    }


@router.put("/organizations/{org_id}/members/{user_id}")
async def update_member(org_id: str, user_id: str, payload: dict, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(UserOrganization).where(UserOrganization.user_id == user_id, UserOrganization.org_id == org_id))
    uo = res.scalar_one_or_none()
    if not uo:
        raise HTTPException(404, "成员不存在")
    if "role_in_org" in payload:
        uo.role_in_org = payload["role_in_org"]
        if payload["role_in_org"] == "org_admin":
            await db.execute(text("UPDATE users SET is_org_admin = 1 WHERE id = :uid"), {"uid": user_id})
        else:
            await db.execute(text("UPDATE users SET is_org_admin = 0 WHERE id = :uid"), {"uid": user_id})
    if "department_id" in payload:
        uo.department_id = payload["department_id"]
    await db.commit()
    return {"user_id": user_id, "role_in_org": uo.role_in_org}


@router.delete("/organizations/{org_id}/members/{user_id}")
async def remove_member(org_id: str, user_id: str, user: User = Depends(require_org_access), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(UserOrganization).where(UserOrganization.user_id == user_id, UserOrganization.org_id == org_id))
    uo = res.scalar_one_or_none()
    if not uo:
        raise HTTPException(404, "成员不存在")
    await db.delete(uo)
    await db.execute(text("UPDATE users SET is_org_admin = 0 WHERE id = :uid AND organization_id = :oid"), {"uid": user_id, "oid": org_id})
    await db.execute(text("UPDATE organizations SET used_seats = (SELECT COUNT(*) FROM user_organizations WHERE org_id = :oid) WHERE id = :oid"), {"oid": org_id})
    await db.commit()
    return {"removed": user_id}

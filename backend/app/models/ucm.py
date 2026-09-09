from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 用户管理子系统 (UCM) 数据模型
包含：组织树 / 部门 / 用户组织关联 / 功能模块 / 套餐 / 套餐功能 / 单项开通 /
      订单 / 订单明细 / 退款 / 资金流水 / 用户等级 / 等级变更日志
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Enum, Text, JSON, Numeric, Date, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.db.session import Base


def generate_uuid():
    """生成UUID"""
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────
# 1. 组织 / 部门 / 成员
# ─────────────────────────────────────────────────────────────

class Organization(Base):
    """企业租户（支持集团-子公司多级树）"""
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # 组织编码
    parent_id = Column(String(36), ForeignKey("organizations.id"), nullable=True)  # 自引用
    level = Column(Integer, default=0)  # 层级深度 0=根
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # 租户管理员
    plan_id = Column(String(36), ForeignKey("plans.id"), nullable=True)  # 当前套餐
    status = Column(String(20), default="active", index=True)  # active/suspended
    max_seats = Column(Integer, default=5)  # 席位数上限
    used_seats = Column(Integer, default=0)  # 已用席位
    expire_at = Column(DateTime(timezone=True), nullable=True)  # 套餐到期
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    parent = relationship("Organization", remote_side=[id], backref="children")
    owner = relationship("User", foreign_keys=[owner_user_id])
    members = relationship("UserOrganization", back_populates="organization", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_org_parent", "parent_id"),
        Index("ix_org_status", "status"),
    )

    def __repr__(self):
        return f"<Organization {self.name}>"


class Department(Base):
    """部门（租户内多级树）"""
    __tablename__ = "departments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    parent_id = Column(String(36), ForeignKey("departments.id"), nullable=True)  # 部门树
    leader_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    organization = relationship("Organization", backref="departments")
    parent = relationship("Department", remote_side=[id], backref="children")

    __table_args__ = (
        Index("ix_dept_org", "org_id"),
        Index("ix_dept_parent", "parent_id"),
    )

    def __repr__(self):
        return f"<Department {self.name}>"


class UserOrganization(Base):
    """用户-组织-部门 关联（多对多，带组织内角色）"""
    __tablename__ = "user_organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True)
    role_in_org = Column(String(20), default="member")  # org_admin/dept_manager/member
    joined_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    user = relationship("User", backref="org_memberships")
    organization = relationship("Organization", back_populates="members")

    __table_args__ = (
        Index("ix_uo_user_org", "user_id", "org_id", unique=True),
    )

    def __repr__(self):
        return f"<UserOrganization user={self.user_id} org={self.org_id}>"


# ─────────────────────────────────────────────────────────────
# 2. 功能模块 / 套餐 / 套餐功能映射 / 单项开通
# ─────────────────────────────────────────────────────────────

class Feature(Base):
    """系统功能模块"""
    __tablename__ = "features"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(50), unique=True, nullable=False, index=True)  # ai_agent/gantt/risk...
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), default="general")  # ai/project/analysis/collab
    is_addon = Column(Boolean, default=False)  # 是否支持单项增购
    price_monthly = Column(Numeric(10, 2), default=0)  # 单项月价
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    def __repr__(self):
        return f"<Feature {self.code}>"


class Plan(Base):
    """套餐（捆绑功能包）"""
    __tablename__ = "plans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # free/basic/pro/enterprise
    price_monthly = Column(Numeric(10, 2), default=0)
    price_yearly = Column(Numeric(10, 2), default=0)
    max_seats = Column(Integer, default=5)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    features = relationship("PlanFeature", back_populates="plan", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Plan {self.name}>"


class PlanFeature(Base):
    """套餐-功能映射"""
    __tablename__ = "plan_features"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    plan_id = Column(String(36), ForeignKey("plans.id"), nullable=False, index=True)
    feature_id = Column(String(36), ForeignKey("features.id"), nullable=False, index=True)
    included = Column(Boolean, default=True)  # 套餐是否包含
    limit_value = Column(Integer, nullable=True)  # 用量上限（如AI调用次数）

    plan = relationship("Plan", back_populates="features")
    feature = relationship("Feature")

    __table_args__ = (
        Index("ix_pf_plan_feature", "plan_id", "feature_id", unique=True),
    )

    def __repr__(self):
        return f"<PlanFeature plan={self.plan_id} feature={self.feature_id}>"


class UserFeatureGrant(Base):
    """单项增购 / 单独开通（套餐之外）"""
    __tablename__ = "user_feature_grants"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    feature_id = Column(String(36), ForeignKey("features.id"), nullable=False, index=True)
    granted_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    granted_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    expire_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text, nullable=True)

    organization = relationship("Organization", backref="feature_grants")
    feature = relationship("Feature")

    __table_args__ = (
        Index("ix_ufg_org_feature", "org_id", "feature_id"),
    )

    def __repr__(self):
        return f"<UserFeatureGrant org={self.org_id} feature={self.feature_id}>"


# ─────────────────────────────────────────────────────────────
# 3. 收费退费
# ─────────────────────────────────────────────────────────────

class Order(Base):
    """订单（后台手动记账）"""
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # 操作人
    type = Column(String(20), default="subscribe")  # subscribe/renew/upgrade/addon
    plan_id = Column(String(36), ForeignKey("plans.id"), nullable=True)
    amount = Column(Numeric(12, 2), default=0)
    currency = Column(String(10), default="CNY")
    status = Column(String(20), default="unpaid", index=True)  # unpaid/paid/refunded/partial_refunded
    payment_method = Column(String(30), nullable=True)  # manual_wechat/manual_alipay/manual_bank/manual_cash
    paid_at = Column(DateTime(timezone=True), nullable=True)
    remark = Column(Text, nullable=True)
    invoice_no = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    organization = relationship("Organization", backref="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_order_org_status", "org_id", "status"),
    )

    def __repr__(self):
        return f"<Order {self.id} {self.status}>"


class OrderItem(Base):
    """订单明细"""
    __tablename__ = "order_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False, index=True)
    item_type = Column(String(20), default="plan")  # plan/addon/seat
    ref_id = Column(String(36), nullable=True)  # 关联 plan/feature id
    name = Column(String(255), nullable=False)
    amount = Column(Numeric(12, 2), default=0)
    quantity = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    order = relationship("Order", back_populates="items")

    def __repr__(self):
        return f"<OrderItem {self.name}>"


class Refund(Base):
    """退款"""
    __tablename__ = "refunds"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False, index=True)
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), default=0)
    reason = Column(Text, nullable=True)
    method = Column(String(30), nullable=True)
    status = Column(String(20), default="pending", index=True)  # pending/approved/rejected/done
    handled_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    handled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    order = relationship("Order", backref="refunds")
    organization = relationship("Organization", backref="refunds")

    __table_args__ = (
        Index("ix_refund_status", "status"),
    )

    def __repr__(self):
        return f"<Refund {self.id} {self.status}>"


class Transaction(Base):
    """资金流水（统一记账）"""
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    org_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    type = Column(String(20), default="income")  # income/refund
    ref_id = Column(String(36), nullable=True)  # 关联 order/refund id
    amount = Column(Numeric(12, 2), default=0)
    balance_after = Column(Numeric(12, 2), default=0)  # 组织账户余额
    operator = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    organization = relationship("Organization", backref="transactions")

    __table_args__ = (
        Index("ix_txn_org_time", "org_id", "created_at"),
    )

    def __repr__(self):
        return f"<Transaction {self.type} {self.amount}>"


# ─────────────────────────────────────────────────────────────
# 4. 用户等级
# ─────────────────────────────────────────────────────────────

class UserLevel(Base):
    """用户等级定义"""
    __tablename__ = "user_levels"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(20), unique=True, nullable=False, index=True)  # free/basic/pro/enterprise
    name = Column(String(255), nullable=False)
    min_points = Column(Integer, default=0)  # 晋升积分阈值
    benefits = Column(Text, nullable=True)  # 权益说明
    icon = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    def __repr__(self):
        return f"<UserLevel {self.code}>"


class UserLevelRecord(Base):
    """用户等级变更日志"""
    __tablename__ = "user_level_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    from_level = Column(String(20), nullable=True)
    to_level = Column(String(20), nullable=False)
    reason = Column(String(50), nullable=True)  # pay/growth/manual
    operator = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    user = relationship("User", foreign_keys=[user_id], backref="level_records")

    __table_args__ = (
        Index("ix_ulr_user", "user_id"),
    )

    def __repr__(self):
        return f"<UserLevelRecord {self.user_id} {self.from_level}->{self.to_level}>"

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class ZapierSubscription(Base):
    """Zapier Webhook 订阅（持久化，避免内存存储导致重启丢失）"""

    __tablename__ = "zapier_subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    trigger_id = Column(String(50), nullable=False, index=True)
    hook_url = Column(String(500), nullable=False)
    secret = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

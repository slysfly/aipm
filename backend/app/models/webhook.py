from sqlalchemy import Column, String, Boolean, DateTime, Text, JSON, Integer, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.db.session import Base


def generate_uuid():
    return str(uuid.uuid4())


class Webhook(Base):
    __tablename__ = "webhooks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    url = Column(String(500), nullable=False)
    secret = Column(String(255), nullable=False)
    events = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_triggered_at = Column(DateTime(timezone=True))
    last_status = Column(String(20), default="pending")
    failure_count = Column(Integer, default=0)

    project = relationship("Project")
    creator = relationship("User")

    __table_args__ = (
        Index("ix_webhook_project_active", "project_id", "is_active"),
            )

    def __repr__(self):
        return f"<Webhook {self.name}>"


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    webhook_id = Column(String(36), ForeignKey("webhooks.id"), nullable=False, index=True)
    event = Column(String(50), nullable=False)
    payload = Column(JSON)
    request_headers = Column(JSON)
    response_status = Column(Integer)
    response_body = Column(Text)
    duration_ms = Column(Integer)
    success = Column(Boolean, default=False)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    webhook = relationship("Webhook")

    __table_args__ = (
        Index("ix_webhook_delivery_webhook", "webhook_id", "created_at"),
        Index("ix_webhook_delivery_event", "event", "created_at"),
    )

    def __repr__(self):
        return f"<WebhookDelivery {self.webhook_id} {self.event}>"

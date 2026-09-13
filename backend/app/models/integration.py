from sqlalchemy import Column, String, DateTime, JSON, Index
from sqlalchemy.sql import func
from app.db.session import Base
import uuid


def generate_uuid():
    return str(uuid.uuid4())


class Integration(Base):
    __tablename__ = "integrations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    provider = Column(String(50), nullable=False, index=True)
    access_token = Column(String(1000))
    refresh_token = Column(String(1000))
    expires_at = Column(DateTime(timezone=True))
    status = Column(String(20), default="disconnected")
    config = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_integration_user_provider", "user_id", "provider", unique=True),
    )

    def __repr__(self):
        return f"<Integration {self.provider}@{self.user_id[:8]}>"

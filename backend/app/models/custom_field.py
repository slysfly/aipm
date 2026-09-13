from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class CustomField(Base):
    __tablename__ = "custom_fields"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    field_key = Column(String(100), nullable=False, index=True)
    field_type = Column(String(20), nullable=False)
    entity_type = Column(String(20), nullable=False, index=True)
    options = Column(JSON, default=list)
    is_required = Column(Boolean, default=False)
    default_value = Column(JSON)
    sort_order = Column(Integer, default=0)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    is_global = Column(Boolean, default=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project")
    creator = relationship("User")
    values = relationship("CustomFieldValue", back_populates="custom_field", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_custom_field_project_entity", "project_id", "entity_type"),
        Index("ix_custom_field_global_entity", "is_global", "entity_type"),
        Index("ix_custom_field_key_project", "field_key", "project_id", unique=True),
    )

    def __repr__(self):
        return f"<CustomField {self.field_key}>"


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    custom_field_id = Column(String(36), ForeignKey("custom_fields.id"), nullable=False, index=True)
    entity_id = Column(String(36), nullable=False, index=True)
    entity_type = Column(String(20), nullable=False, index=True)
    value = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    custom_field = relationship("CustomField", back_populates="values")

    __table_args__ = (
        Index("ix_custom_field_value_entity", "entity_id", "entity_type"),
        Index("ix_custom_field_value_unique", "custom_field_id", "entity_id", "entity_type", unique=True),
    )

    def __repr__(self):
        return f"<CustomFieldValue {self.custom_field_id}={self.value}>"

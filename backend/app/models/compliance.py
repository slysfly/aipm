from sqlalchemy import text
"""
PMI中国AI项目管理社区 - SOC2/ISO27001 合规模型
包含合规策略、控制措施、审计记录和证据管理
"""

import enum
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, JSON, Index, Text, Integer, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class ComplianceCategory(str, enum.Enum):
    """合规类别枚举"""
    SECURITY = "security"
    PRIVACY = "privacy"
    AVAILABILITY = "availability"
    CONFIDENTIALITY = "confidentiality"


class ComplianceStatus(str, enum.Enum):
    """合规状态枚举"""
    DRAFT = "draft"
    ACTIVE = "active"
    UNDER_REVIEW = "under_review"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ControlImplementationStatus(str, enum.Enum):
    """控制措施实施状态枚举"""
    NOT_IMPLEMENTED = "not_implemented"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    IMPLEMENTED = "implemented"
    NOT_APPLICABLE = "not_applicable"


class RiskLevel(str, enum.Enum):
    """风险等级枚举"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AuditType(str, enum.Enum):
    """审计类型枚举"""
    SCHEDULED = "scheduled"
    AD_HOC = "ad_hoc"
    FOLLOW_UP = "follow_up"


class AuditStatus(str, enum.Enum):
    """审计状态枚举"""
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class CompliancePolicy(Base):
    """合规策略表"""
    __tablename__ = "compliance_policies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    category = Column(String(50), default=ComplianceCategory.SECURITY.value, index=True)
    status = Column(String(20), default=ComplianceStatus.DRAFT.value, index=True)
    version = Column(String(20), default="1.0")
    effective_date = Column(Date)
    review_cycle_days = Column(Integer, default=365)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    document_url = Column(String(500))

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    owner = relationship("User")
    controls = relationship("ComplianceControl", back_populates="policy", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_policy_category_status", "category", "status"),
        Index("ix_policy_owner", "owner_id"),
        Index("ix_policy_effective_date", "effective_date"),
    )

    def __repr__(self):
        return f"<CompliancePolicy {self.title} v{self.version}>"


class ComplianceControl(Base):
    """控制措施表"""
    __tablename__ = "compliance_controls"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    policy_id = Column(String(36), ForeignKey("compliance_policies.id"), nullable=False, index=True)
    control_code = Column(String(50), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    implementation_status = Column(
        String(30),
        default=ControlImplementationStatus.NOT_IMPLEMENTED.value,
        index=True
    )
    evidence_required = Column(Boolean, default=True)
    last_tested_at = Column(DateTime(timezone=True))
    next_test_due = Column(DateTime(timezone=True))
    risk_level = Column(String(20), default=RiskLevel.MEDIUM.value, index=True)

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    policy = relationship("CompliancePolicy", back_populates="controls")
    audits = relationship("ComplianceAudit", back_populates="control", cascade="all, delete-orphan")
    evidences = relationship("ComplianceEvidence", back_populates="control", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_control_policy_status", "policy_id", "implementation_status"),
        Index("ix_control_risk_level", "risk_level"),
        Index("ix_control_next_test_due", "next_test_due"),
    )

    def __repr__(self):
        return f"<ComplianceControl {self.control_code} {self.title}>"


class ComplianceAudit(Base):
    """审计记录表"""
    __tablename__ = "compliance_audits"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    control_id = Column(String(36), ForeignKey("compliance_controls.id"), nullable=False, index=True)
    auditor_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    audit_type = Column(String(20), default=AuditType.SCHEDULED.value, index=True)
    findings = Column(Text)
    status = Column(String(20), default=AuditStatus.PASS.value, index=True)
    evidence_links = Column(JSON, default=list)
    conducted_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    control = relationship("ComplianceControl", back_populates="audits")
    auditor = relationship("User")

    __table_args__ = (
        Index("ix_audit_control_conducted", "control_id", "conducted_at"),
        Index("ix_audit_status", "status"),
        Index("ix_audit_auditor", "auditor_id"),
    )

    def __repr__(self):
        return f"<ComplianceAudit {self.control_id} {self.status}>"


class ComplianceEvidence(Base):
    """证据表"""
    __tablename__ = "compliance_evidences"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    control_id = Column(String(36), ForeignKey("compliance_controls.id"), nullable=False, index=True)
    file_url = Column(String(500), nullable=False)
    description = Column(Text)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    # 关系
    control = relationship("ComplianceControl", back_populates="evidences")
    uploader = relationship("User")

    __table_args__ = (
        Index("ix_evidence_control", "control_id", "created_at"),
        Index("ix_evidence_uploader", "uploaded_by"),
    )

    def __repr__(self):
        return f"<ComplianceEvidence {self.id[:8]} {self.file_url[:30]}>"

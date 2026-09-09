from sqlalchemy import text
"""
PMI中国AI项目管理社区 - 风险预警记录模型
"""

import enum
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base
from app.models import generate_uuid


class RiskAlertType(str, enum.Enum):
    """风险预警类型"""
    SCHEDULE = "schedule"
    RESOURCE = "resource"
    BUDGET = "budget"
    QUALITY = "quality"


class RiskAlertSeverity(str, enum.Enum):
    """风险严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskAlertStatus(str, enum.Enum):
    """风险预警状态"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class RiskAlert(Base):
    """风险预警记录模型"""
    __tablename__ = "risk_alerts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)

    type = Column(String(20), default=RiskAlertType.SCHEDULE.value)
    severity = Column(String(20), default=RiskAlertSeverity.MEDIUM.value)
    message = Column(String(500), nullable=False)
    details = Column(Text)

    status = Column(String(20), default=RiskAlertStatus.ACTIVE.value)
    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    resolved_at = Column(DateTime(timezone=True))

    project = relationship("Project")

    __table_args__ = (
        Index("ix_risk_alert_project_status", "project_id", "status"),
        Index("ix_risk_alert_type_severity", "type", "severity"),
        Index("ix_risk_alert_created", "created_at"),
    )

    def __repr__(self):
        return f"<RiskAlert {self.type} {self.severity} {self.message[:30]}>"

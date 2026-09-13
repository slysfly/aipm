import enum
import uuid

from sqlalchemy import Column, String, Boolean, DateTime, JSON, ForeignKey, Index, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


def generate_uuid():
    return str(uuid.uuid4())


class Permission(str, enum.Enum):
    PROJECT_VIEW = "project.view"
    PROJECT_EDIT = "project.edit"
    PROJECT_DELETE = "project.delete"
    TASK_VIEW = "task.view"
    TASK_CREATE = "task.create"
    TASK_EDIT = "task.edit"
    TASK_DELETE = "task.delete"
    TASK_ASSIGN = "task.assign"
    COMMENT_VIEW = "comment.view"
    COMMENT_CREATE = "comment.create"
    FILE_VIEW = "file.view"
    FILE_UPLOAD = "file.upload"
    FILE_DELETE = "file.delete"
    RISK_VIEW = "risk.view"
    RISK_CREATE = "risk.create"
    RISK_EDIT = "risk.edit"
    SETTINGS_VIEW = "settings.view"
    SETTINGS_EDIT = "settings.edit"
    MEMBER_INVITE = "member.invite"
    MEMBER_REMOVE = "member.remove"


class Role(Base):
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(String(500))
    permissions = Column(JSON, default=list)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    members = relationship("ProjectMember", back_populates="role")

    def has_permission(self, permission: Permission) -> bool:
        if self.permissions is None:
            return False
        return permission.value in self.permissions

    def __repr__(self):
        return f"<Role {self.name}>"


class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role_id = Column(String(36), ForeignKey("roles.id"), nullable=False, index=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    invited_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    project = relationship("Project")
    user = relationship("User", foreign_keys=[user_id])
    role = relationship("Role", back_populates="members")
    inviter = relationship("User", foreign_keys=[invited_by])

    __table_args__ = (
        Index("ix_project_member_unique", "project_id", "user_id", unique=True),
        Index("ix_project_member_role", "project_id", "role_id"),
    )

    def __repr__(self):
        return f"<ProjectMember {self.user_id}@{self.project_id}>"

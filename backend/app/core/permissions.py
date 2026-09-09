from functools import wraps
from typing import Optional, List, Callable

from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.session import get_db
from app.core.security import get_current_user
from app.models import User
from app.models.permission import Permission, Role, ProjectMember


class PermissionDeniedException(HTTPException):
    def __init__(self, detail: str = "权限不足"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


async def check_project_permission(
    db: AsyncSession,
    user_id: str,
    project_id: str,
    permission: Permission
) -> bool:
    if not project_id:
        return False

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user and user.is_superuser:
        return True

    result = await db.execute(
        select(ProjectMember)
        .join(Role)
        .where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_active == True
            )
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        return False

    return member.role.has_permission(permission)


async def get_user_permissions(
    db: AsyncSession,
    user_id: str,
    project_id: Optional[str] = None
) -> List[str]:
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user and user.is_superuser:
        return [p.value for p in Permission]

    if not project_id:
        return []

    result = await db.execute(
        select(ProjectMember)
        .join(Role)
        .where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
                ProjectMember.is_active == True
            )
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        return []

    return member.role.permissions or []


def require_permission(permission: Permission):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            db = kwargs.get("db")
            current_user = kwargs.get("current_user")
            project_id = kwargs.get("project_id")

            if not db or not current_user:
                for arg in args:
                    if isinstance(arg, AsyncSession):
                        db = arg
                    elif isinstance(arg, User):
                        current_user = arg

            if not db or not current_user:
                raise PermissionDeniedException("无法获取用户或数据库会话")

            if current_user.is_superuser:
                return await func(*args, **kwargs)

            if not project_id:
                request = kwargs.get("request")
                if request and isinstance(request, Request):
                    project_id = request.path_params.get("project_id") or request.query_params.get("project_id")

            if not project_id:
                for key, value in kwargs.items():
                    if key in ("project_id", "projectId") and value:
                        project_id = value
                        break

            if not project_id:
                raise PermissionDeniedException("无法确定项目ID")

            has_perm = await check_project_permission(
                db, current_user.id, project_id, permission
            )

            if not has_perm:
                raise PermissionDeniedException(
                    f"需要权限: {permission.value}"
                )

            return await func(*args, **kwargs)
        return wrapper
    return decorator


class PermissionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, protected_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.protected_paths = protected_paths or [
            "/api/v1/projects",
            "/api/v1/tasks",
            "/api/v1/risks",
            "/api/v1/comments",
            "/api/v1/attachments",
        ]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        is_protected = any(
            path.startswith(protected) for protected in self.protected_paths
        )

        if is_protected and request.method in ("POST", "PUT", "DELETE", "PATCH"):
            pass

        response = await call_next(request)
        return response

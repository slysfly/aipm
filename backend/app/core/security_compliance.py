"""
PMI中国AI项目管理社区 - 安全合规工具模块
包含密码策略、数据加密、审计日志、敏感数据脱敏、访问控制
"""

import re
import functools
import hashlib
import logging
from typing import Optional, Callable, Any, Dict, List
from datetime import datetime, timedelta
from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.core.encryption import encrypt_field, decrypt_field
from app.models import User, AuditLog
from app.db.session import get_db

logger = logging.getLogger(__name__)


# ==================== 密码策略 ====================

class PasswordPolicy:
    """密码策略验证器"""

    MIN_LENGTH = 12
    MAX_LENGTH = 128
    REQUIRE_UPPERCASE = True
    REQUIRE_LOWERCASE = True
    REQUIRE_DIGITS = True
    REQUIRE_SPECIAL = True
    SPECIAL_CHARS = r"!@#$%^&*()_+-=[]{}|;:,.<>?"
    PASSWORD_EXPIRY_DAYS = 90

    @classmethod
    def validate(cls, password: str) -> Dict[str, Any]:
        """
        验证密码是否符合策略

        Returns:
            {"valid": bool, "errors": List[str]}
        """
        errors = []

        if len(password) < cls.MIN_LENGTH:
            errors.append(f"密码长度至少为 {cls.MIN_LENGTH} 位")
        if len(password) > cls.MAX_LENGTH:
            errors.append(f"密码长度不能超过 {cls.MAX_LENGTH} 位")
        if cls.REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
            errors.append("密码必须包含至少一个大写字母")
        if cls.REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
            errors.append("密码必须包含至少一个小写字母")
        if cls.REQUIRE_DIGITS and not re.search(r"\d", password):
            errors.append("密码必须包含至少一个数字")
        if cls.REQUIRE_SPECIAL and not re.search(rf"[{re.escape(cls.SPECIAL_CHARS)}]", password):
            errors.append(f"密码必须包含至少一个特殊字符: {cls.SPECIAL_CHARS}")

        # 检查常见弱密码模式
        common_patterns = ["123", "abc", "password", "qwerty", "admin"]
        for pattern in common_patterns:
            if pattern.lower() in password.lower():
                errors.append(f"密码包含常见弱密码模式: '{pattern}'")
                break

        return {"valid": len(errors) == 0, "errors": errors}

    @classmethod
    def check_expiry(cls, last_changed: Optional[datetime]) -> bool:
        """检查密码是否过期"""
        if last_changed is None:
            return True
        expiry_date = last_changed + timedelta(days=cls.PASSWORD_EXPIRY_DAYS)
        return datetime.now() > expiry_date

    @classmethod
    def calculate_strength(cls, password: str) -> Dict[str, Any]:
        """计算密码强度评分"""
        score = 0
        feedback = []

        if len(password) >= cls.MIN_LENGTH:
            score += 20
        else:
            feedback.append("增加密码长度")

        if re.search(r"[A-Z]", password):
            score += 15
        else:
            feedback.append("添加大写字母")

        if re.search(r"[a-z]", password):
            score += 15
        else:
            feedback.append("添加小写字母")

        if re.search(r"\d", password):
            score += 15
        else:
            feedback.append("添加数字")

        if re.search(rf"[{re.escape(cls.SPECIAL_CHARS)}]", password):
            score += 15
        else:
            feedback.append("添加特殊字符")

        if len(password) >= 16:
            score += 20
        elif len(password) >= 14:
            score += 10

        strength_label = "weak"
        if score >= 80:
            strength_label = "strong"
        elif score >= 50:
            strength_label = "medium"

        return {
            "score": score,
            "strength": strength_label,
            "feedback": feedback,
        }


# ==================== 审计日志装饰器 ====================

def audit_log(
    action: str,
    entity_type: Optional[str] = None,
    get_entity_id: Optional[Callable] = None,
):
    """
    审计日志装饰器

    Args:
        action: 操作类型，如 "create", "update", "delete", "test_control"
        entity_type: 实体类型，如 "compliance_policy", "compliance_control"
        get_entity_id: 可选的函数，用于从参数中提取 entity_id
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            try:
                db: Optional[AsyncSession] = kwargs.get("db")
                current_user: Optional[User] = kwargs.get("current_user")
                request: Optional[Request] = kwargs.get("request")

                if not db:
                    for arg in args:
                        if isinstance(arg, AsyncSession):
                            db = arg
                            break

                if db and current_user:
                    entity_id = None
                    if get_entity_id:
                        entity_id = get_entity_id(*args, **kwargs)
                    elif result and hasattr(result, "id"):
                        entity_id = str(result.id)
                    elif isinstance(result, dict) and "id" in result:
                        entity_id = str(result["id"])

                    ip_address = None
                    user_agent = None
                    if request:
                        ip_address = _get_client_ip(request)
                        user_agent = request.headers.get("user-agent")

                    log_entry = AuditLog(
                        user_id=current_user.id,
                        action=action,
                        entity_type=entity_type or func.__name__,
                        entity_id=entity_id or "unknown",
                        changes={"function": func.__name__},
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )
                    db.add(log_entry)
                    await db.commit()
            except Exception as e:
                logger.error(f"审计日志记录失败: {e}")

            return result
        return wrapper
    return decorator


def _get_client_ip(request: Request) -> str:
    """获取客户端真实IP"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ==================== 敏感数据脱敏 ====================

def mask_email(email: str) -> str:
    """脱敏邮箱地址"""
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def mask_phone(phone: str) -> str:
    """脱敏手机号"""
    if not phone or len(phone) < 7:
        return "***"
    return phone[:3] + "****" + phone[-4:]


def mask_id_card(id_card: str) -> str:
    """脱敏身份证号"""
    if not id_card or len(id_card) < 8:
        return "***"
    return id_card[:4] + "**********" + id_card[-4:]


def mask_bank_card(bank_card: str) -> str:
    """脱敏银行卡号"""
    if not bank_card or len(bank_card) < 8:
        return "***"
    return bank_card[:4] + " **** **** " + bank_card[-4:]


def mask_string(value: str, visible_head: int = 2, visible_tail: int = 2) -> str:
    """通用字符串脱敏"""
    if not value or len(value) <= visible_head + visible_tail:
        return "*" * len(value) if value else ""
    return value[:visible_head] + "*" * (len(value) - visible_head - visible_tail) + value[-visible_tail:]


def mask_dict(data: Dict[str, Any], sensitive_fields: List[str]) -> Dict[str, Any]:
    """
    对字典中的敏感字段进行脱敏

    Args:
        data: 原始数据字典
        sensitive_fields: 需要脱敏的字段名列表

    Returns:
        脱敏后的字典
    """
    result = {}
    for key, value in data.items():
        if key in sensitive_fields:
            if isinstance(value, str):
                if "email" in key.lower():
                    result[key] = mask_email(value)
                elif "phone" in key.lower() or "mobile" in key.lower():
                    result[key] = mask_phone(value)
                elif "password" in key.lower() or "secret" in key.lower() or "token" in key.lower():
                    result[key] = "********"
                else:
                    result[key] = mask_string(value)
            else:
                result[key] = "***"
        elif isinstance(value, dict):
            result[key] = mask_dict(value, sensitive_fields)
        elif isinstance(value, list):
            result[key] = [
                mask_dict(item, sensitive_fields) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


# ==================== 访问控制（RBAC + ABAC） ====================

class AccessControl:
    """访问控制检查器"""

    @staticmethod
    def check_rbac(
        user: User,
        required_roles: List[str],
        required_permissions: Optional[List[str]] = None,
    ) -> bool:
        """
        基于角色的访问控制检查

        Args:
            user: 当前用户
            required_roles: 所需角色列表
            required_permissions: 所需权限列表

        Returns:
            是否有权限
        """
        if user.is_superuser:
            return True

        # 检查角色
        user_roles = getattr(user, "roles", []) or []
        user_role_names = [r.name if hasattr(r, "name") else str(r) for r in user_roles]
        has_role = any(role in user_role_names for role in required_roles)

        if not has_role and required_roles:
            return False

        # 检查权限
        if required_permissions:
            user_perms = getattr(user, "permissions", []) or []
            user_perm_values = [p.value if hasattr(p, "value") else str(p) for p in user_perms]
            has_perm = all(perm in user_perm_values for perm in required_permissions)
            return has_perm

        return True

    @staticmethod
    def check_abac(
        user: User,
        resource: Any,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        基于属性的访问控制检查

        Args:
            user: 当前用户
            resource: 被访问的资源
            action: 操作类型
            context: 额外上下文

        Returns:
            是否有权限
        """
        if user.is_superuser:
            return True

        context = context or {}

        # 资源所有者检查
        owner_id = getattr(resource, "owner_id", None) or getattr(resource, "created_by", None)
        if owner_id and str(owner_id) == str(user.id):
            return True

        # 部门检查
        user_dept = getattr(user, "department", None)
        resource_dept = getattr(resource, "department", None)
        if user_dept and resource_dept and user_dept == resource_dept:
            # 同部门用户有读权限
            if action in ("view", "read", "list"):
                return True

        # 时间限制检查（如仅工作时间允许操作）
        time_restricted = context.get("time_restricted", False)
        if time_restricted:
            now = datetime.now()
            if now.weekday() >= 5:  # 周末
                return False
            hour = now.hour
            if hour < 9 or hour > 18:
                return False

        # IP限制检查
        allowed_ips = context.get("allowed_ips")
        client_ip = context.get("client_ip")
        if allowed_ips and client_ip and client_ip not in allowed_ips:
            return False

        return False

    @staticmethod
    def check_combined(
        user: User,
        required_roles: Optional[List[str]] = None,
        required_permissions: Optional[List[str]] = None,
        resource: Optional[Any] = None,
        action: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        组合 RBAC + ABAC 检查

        Returns:
            是否有权限
        """
        if user.is_superuser:
            return True

        # RBAC 检查
        if required_roles or required_permissions:
            rbac_pass = AccessControl.check_rbac(user, required_roles or [], required_permissions)
            if not rbac_pass:
                return False

        # ABAC 检查
        if resource and action:
            abac_pass = AccessControl.check_abac(user, resource, action, context)
            if not abac_pass:
                return False

        return True


def require_compliance_role(
    required_roles: Optional[List[str]] = None,
    required_permissions: Optional[List[str]] = None,
):
    """
    合规模块权限依赖

    Args:
        required_roles: 所需角色，如 ["compliance_officer", "admin"]
        required_permissions: 所需权限
    """
    from app.core.security import get_current_user

    async def checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        roles = required_roles or ["compliance_officer", "admin", "auditor"]
        perms = required_permissions or []

        if not AccessControl.check_combined(
            current_user, required_roles=roles, required_permissions=perms
        ):
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，需要合规相关角色",
            )
        return current_user

    return checker


# ==================== 哈希工具 ====================

def hash_sensitive_value(value: str, salt: Optional[str] = None) -> str:
    """
    对敏感值进行单向哈希（用于日志中标识但不暴露原始值）

    Args:
        value: 原始值
        salt: 可选的盐值

    Returns:
        SHA-256 哈希值
    """
    salted = f"{value}:{salt or settings.SECRET_KEY[:16]}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()[:16]

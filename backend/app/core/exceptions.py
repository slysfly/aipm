"""
PMI中国AI项目管理社区 - 核心异常定义
"""

from typing import Any, Dict, Optional


class ProjectManagementException(Exception):
    """项目管理基础异常"""
    
    def __init__(
        self,
        message: str,
        code: str = "PM_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.details = details
        super().__init__(self.message)


class NotFoundException(ProjectManagementException):
    """资源不存在异常"""
    
    def __init__(
        self,
        message: str = "资源不存在",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="NOT_FOUND",
            details=details
        )


class ValidationException(ProjectManagementException):
    """数据验证异常"""
    
    def __init__(
        self,
        message: str = "数据验证失败",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details=details
        )


class AuthenticationException(ProjectManagementException):
    """认证异常"""
    
    def __init__(
        self,
        message: str = "认证失败",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            details=details
        )


class AuthorizationException(ProjectManagementException):
    """权限异常"""
    
    def __init__(
        self,
        message: str = "权限不足",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
            details=details
        )


class BusinessException(ProjectManagementException):
    """业务逻辑异常"""
    
    def __init__(
        self,
        message: str,
        code: str = "BUSINESS_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code=code,
            details=details
        )


class CircularDependencyException(BusinessException):
    """循环依赖异常"""
    
    def __init__(
        self,
        message: str = "检测到循环依赖",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="CIRCULAR_DEPENDENCY",
            details=details
        )


class ResourceOverloadException(BusinessException):
    """资源过载异常"""
    
    def __init__(
        self,
        message: str = "资源分配超过容量",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            code="RESOURCE_OVERLOAD",
            details=details
        )

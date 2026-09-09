"""
PMI中国AI项目管理社区 — 统一响应格式

强制所有 API 接口使用统一的响应信封：
    { "code": 200, "data": ..., "message": "ok" }

- 成功响应用 success()
- 错误响应用 error()
- 分页数据用 paginated()
- 文件流用 FileResponse（不需要包装）
"""

from typing import Any, Dict, List, Optional, TypeVar
from fastapi.responses import JSONResponse
from fastapi import status

T = TypeVar("T")


def success(
    data: Any = None,
    message: str = "ok",
    code: int = status.HTTP_200_OK,
) -> JSONResponse:
    """成功响应"""
    body: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        body["data"] = data
    return JSONResponse(status_code=code, content=body)


def created(
    data: Any = None,
    message: str = "created",
) -> JSONResponse:
    """创建成功响应 (201)"""
    return success(data=data, message=message, code=status.HTTP_201_CREATED)


def paginated(
    items: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
    message: str = "ok",
) -> JSONResponse:
    """分页列表响应"""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "code": 200,
            "message": message,
            "data": {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        },
    )


def error(
    message: str = "error",
    code: int = status.HTTP_400_BAD_REQUEST,
    details: Any = None,
) -> JSONResponse:
    """错误响应"""
    body = error_dict(message=message, code=code, details=details)
    return JSONResponse(status_code=code, content=body)


# ============================================================
# Dict helpers — 在 exception handler / route handler 内部使用
# 返回纯字典，由调用方自行决定如何包装为 Response
# ============================================================

def ok_dict(data: Any = None, message: str = "ok") -> Dict[str, Any]:
    """纯字典格式的成功数据"""
    rv: Dict[str, Any] = {"code": 200, "message": message}
    if data is not None:
        rv["data"] = data
    return rv


def error_dict(
    message: str = "error",
    code: int = status.HTTP_400_BAD_REQUEST,
    details: Any = None,
) -> Dict[str, Any]:
    """纯字典格式的错误数据"""
    body: Dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return body

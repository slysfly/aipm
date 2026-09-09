"""
统一 API 响应信封助手（标准 v2）

所有新接口应优先使用本模块返回的"信封"字典，由 FastAPI 自动序列化为 JSON：
    { "code": 0, "message": "ok", "data": ... }

约定：
- 成功响应用 success() / paginated()
- 业务错误用 fail()（抛 HTTPException，detail 内携带 {code, message}）
- 前端 http.ts 的 unwrap() 已兼容 {code, data} 与 {data} 两种形态，
  因此只要 data 字段内容不变即为安全改造。

注意：本模块返回纯 dict，区别于 app/core/response.py（返回 JSONResponse）。
"""

from typing import Any, Dict, List, Optional

from fastapi import HTTPException


def success(data: Any = None, message: str = "ok", code: int = 0) -> Dict[str, Any]:
    """
    成功响应信封。

    :param data: 业务数据负载，可为 None（如删除成功）
    :param message: 提示信息，默认 "ok"
    :param code: 业务状态码，0 表示成功
    :return: {"code": code, "message": message, "data": data}
    """
    return {"code": code, "message": message, "data": data}


def fail(message: str, code: int = 1, status_code: int = 400) -> None:
    """
    抛出统一格式的业务错误。

    将 {code, message} 置于 HTTPException.detail 中，前端 error 处理可据此解析。
    """
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def paginated(
    items: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """
    分页列表响应信封。

    :return: {"code":0,"message":"ok","data":{"items":...,"total":...,"page":...,"page_size":...}}
    """
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }

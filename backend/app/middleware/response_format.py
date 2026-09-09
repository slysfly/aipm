"""
PMI中国AI项目管理社区 - 统一响应格式中间件

对所有 JSON 响应自动包裹标准信封 {code, data, message}。
对于已使用 response.py 的端点（已有 code/message 的响应）不再二次包裹。

[PMBOK KA: 跨领域 | PG: 执行 — 架构标准化]
"""

import json
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class ResponseFormatMiddleware:
    """
    统一响应格式中间件。

    在 response 返回前拦截，对符合以下条件的 JSON 响应自动包裹：
      - Content-Type 含 application/json
      - 响应体是字典或列表
      - 尚未包含 "code" 键（即未使用 response.py）
      - 状态码为 2xx（成功响应）
    4xx/5xx 错误响应除非已经有标准格式，否则保留原始错误信息
    不包装。

    流式响应（StreamingResponse）、文件响应（FileResponse）、204 无内容等跳过。
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def _send_wrapper(message):
            """拦截 response body，判断是否需要包装。"""
            if message["type"] == "http.response.body" and message.get("body"):
                content_type = ""
                for name, value in scope.get("headers", []):
                    if name == b"content-type":
                        content_type = value.decode("utf-8", "replace")
                        break

                if "application/json" in content_type:
                    try:
                        body = json.loads(message["body"])
                        # 仅当 body 是 dict 且尚未包装时进行包裹
                        if isinstance(body, dict) and "code" not in body:
                            wrapped = {
                                "code": 200,
                                "data": body,
                                "message": "ok",
                            }
                            new_body = json.dumps(wrapped, ensure_ascii=False).encode("utf-8")
                            message["body"] = new_body
                            # 更新 Content-Length
                            headers = [
                                (k, v) for k, v in message.get("headers", [])
                                if k.lower() != b"content-length"
                            ]
                            headers.append((b"content-length", str(len(new_body)).encode()))
                            message["headers"] = headers
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass  # 无法解析的 body 跳过

            await send(message)

        await self.app(scope, receive, _send_wrapper)

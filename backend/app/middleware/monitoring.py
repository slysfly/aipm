"""
PMI中国AI项目管理社区 - 监控中间件
记录请求处理时间、状态码分布、慢查询
"""

import time
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.monitoring import metrics_collector

logger = logging.getLogger(__name__)


class MonitoringMiddleware(BaseHTTPMiddleware):
    """监控中间件 - 记录每个请求的处理时间和状态码"""

    def __init__(self, app: ASGIApp, slow_query_threshold_ms: float = 500.0):
        super().__init__(app)
        self.slow_query_threshold_ms = slow_query_threshold_ms

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求并记录指标"""
        start_time = time.time()

        # 记录请求开始
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            status_code = response.status_code

            # 计算处理时间
            duration_ms = (time.time() - start_time) * 1000

            # 记录请求指标
            metrics_collector.record_request(
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            )

            # 记录慢请求
            if duration_ms >= self.slow_query_threshold_ms:
                logger.warning(
                    f"🐌 慢请求: {method} {path} - {duration_ms:.2f}ms (状态码: {status_code})"
                )

            # 添加监控响应头
            response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))

            return response

        except Exception as exc:
            # 计算处理时间（即使出错）
            duration_ms = (time.time() - start_time) * 1000

            # 记录错误请求
            metrics_collector.record_request(
                method=method,
                path=path,
                status_code=500,
                duration_ms=duration_ms,
            )
            metrics_collector.record_error(
                error_type=type(exc).__name__,
                message=f"{method} {path}: {str(exc)}",
            )

            logger.error(f"❌ 请求异常: {method} {path} - {exc}")
            raise

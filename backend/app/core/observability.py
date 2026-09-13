"""
PMI中国AI项目管理社区 - 可观测性基础设施

提供三类能力：Prometheus 指标与 OTel 链路追踪由环境变量门控且默认关闭；
日志关联（X-Request-ID 注入）始终开启——默认文本日志格式会追加 [request_id] 段，
结构化 JSON 由 LOG_JSON 控制：
1. Log：X-Request-ID 生成/透传（contextvar），供日志关联同一请求的完整链路
2. Metrics：Prometheus 标准指标与 /metrics 暴露端点（METRICS_ENABLED 控制）
3. Trace：OpenTelemetry OTLP 导出（OTEL_ENABLED 控制，依赖见 requirements-observability.txt）

注意：request_id 与 JSON 格式的作用范围是应用日志（经 root handlers 输出的 logger）；
uvicorn 自身的 access 日志有独立 handler 与 propagate=False，不在此列。

与既有体系的关系（注意：不要重复建设）：
- app/core/logging.py 仍负责日志输出（控制台 + 轮转文件），本模块为其提供 request_id 注入
  与 JSON 格式扩展（LOG_JSON=true）
- app/core/monitoring.py 的内存指标收集器（/api/v1/monitoring/* JSON 端点）保持不动，
  本模块补充的是 Prometheus 标准暴露格式，便于直接接入 Grafana/Prometheus 生态
- /health 端点已存在（app/main.py），此处不重复提供
"""

import hmac
import logging
import time
import uuid
import contextvars

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)

# 当前请求的请求 ID（"-" 表示不在请求上下文中，如启动期/定时任务）
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# ---------------------------------------------------------------------------
# Prometheus 指标（prometheus_client 未安装时自动降级为 no-op，仅记录 warning）
# ---------------------------------------------------------------------------
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST, REGISTRY, Counter, Gauge, Histogram, generate_latest,
    )
    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖缺失时的降级路径
    _PROM_AVAILABLE = False
    logger.warning("prometheus_client 未安装，Prometheus 指标已降级为 no-op（pip install prometheus-client）")

if _PROM_AVAILABLE:
    # route 标签使用路由模板（如 /api/v1/projects/{id}）而非原始路径，避免标签基数爆炸
    HTTP_REQUESTS_TOTAL = Counter(
        "aipm_http_requests_total", "HTTP 请求总数", ["method", "route", "status"],
    )
    HTTP_REQUEST_DURATION = Histogram(
        "aipm_http_request_duration_seconds", "HTTP 请求耗时（秒）", ["method", "route"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    )
    HTTP_IN_FLIGHT = Gauge("aipm_http_requests_in_flight", "当前在途请求数")
    HTTP_EXCEPTIONS = Counter(
        "aipm_http_exceptions_total", "未处理异常总数", ["method", "route", "type"],
    )


def _route_template(request: Request) -> str:
    """取路由模板作为指标标签；未匹配路由的请求统一记为 <unmatched> 控制基数"""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or "<unmatched>"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """请求上下文中间件：生成/透传 X-Request-ID，并记录 Prometheus 指标。

    - 入站带 X-Request-ID 则透传（便于接入网关/前端生成的链路 ID），否则生成 16 位 hex
    - 响应头回写 X-Request-ID，日志经 RequestIdFilter 即可关联（见 app/core/logging.py）
    - prometheus_client 可用时记录请求计数/耗时直方图/在途数/异常计数
    """

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        request.state.request_id = rid
        start = time.perf_counter()
        if _PROM_AVAILABLE:
            HTTP_IN_FLIGHT.inc()
        try:
            response = await call_next(request)
            route = _route_template(request)
            # 探活/抓取请求自身不计入业务指标，避免 Prometheus 周期抓取抬高请求计数
            if _PROM_AVAILABLE and request.url.path not in ("/metrics", "/health"):
                HTTP_REQUESTS_TOTAL.labels(request.method, route, str(response.status_code)).inc()
                HTTP_REQUEST_DURATION.labels(request.method, route).observe(time.perf_counter() - start)
            response.headers["X-Request-ID"] = rid
            return response
        except Exception as exc:
            # 注意：此处记 500 与两个入口的 general_exception_handler 固定返回 500 相耦合；
            # 若未来该 handler 返回其他状态码（如 503 降级），指标会与之偏离。
            # 客户端断连（asyncio.CancelledError 属 BaseException）不走本分支，属已知盲区。
            route = _route_template(request)
            if _PROM_AVAILABLE:
                HTTP_EXCEPTIONS.labels(request.method, route, type(exc).__name__).inc()
                HTTP_REQUESTS_TOTAL.labels(request.method, route, "500").inc()
                HTTP_REQUEST_DURATION.labels(request.method, route).observe(time.perf_counter() - start)
            raise
        finally:
            request_id_var.reset(token)
            if _PROM_AVAILABLE:
                HTTP_IN_FLIGHT.dec()


def _init_tracing(app: FastAPI) -> None:
    """初始化 OpenTelemetry（依赖未安装时 warning 并跳过，不影响启动）"""
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "OTEL_ENABLED=1 但未安装 OpenTelemetry 依赖（见 requirements-observability.txt），链路追踪已跳过"
        )
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": f"aipm-{settings.ENVIRONMENT}"})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    logger.info(f"OpenTelemetry 已启用，OTLP 端点: {settings.OTEL_EXPORTER_OTLP_ENDPOINT}")

    # 可选的下游插桩（依赖存在才生效）
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument()
    except ImportError:
        pass


def setup_observability(app: FastAPI) -> None:
    """统一接线入口（app/main.py 与 serve.py 各调用一次）"""
    app.add_middleware(RequestContextMiddleware)

    if settings.METRICS_ENABLED:
        if not _PROM_AVAILABLE:
            logger.warning("METRICS_ENABLED=1 但 prometheus_client 未安装，/metrics 端点将返回 501")

        @app.get("/metrics", include_in_schema=False)
        async def prometheus_metrics(request: Request) -> Response:
            # 可选 Bearer Token 保护；未配置时假定 /metrics 仅在内网/被网关拦截
            if settings.METRICS_TOKEN:
                auth = request.headers.get("authorization", "")
                expected = f"Bearer {settings.METRICS_TOKEN}"
                if not hmac.compare_digest(auth, expected):
                    return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
            if not _PROM_AVAILABLE:
                return Response("prometheus_client 未安装：pip install prometheus-client", status_code=501)
            # Content-Type 必须用 headers 显式给出：media_type= 会让 Starlette 追加
            # charset=utf-8，与 CONTENT_TYPE_LATEST 自带的 charset 重复，
            # 真实 Prometheus 服务端解析 Content-Type 时会因重复参数拒收
            return Response(
                generate_latest(REGISTRY),
                headers={"Content-Type": CONTENT_TYPE_LATEST},
            )

        logger.info("Prometheus /metrics 端点已启用" + ("（已配置访问令牌）" if settings.METRICS_TOKEN else ""))

    if settings.OTEL_ENABLED:
        _init_tracing(app)

"""
AIPM 后端 · 运维可观测性（Issue #19 阶段一 / 阶段二）

阶段一：X-Request-ID 请求关联（请求进入即确定，透传或生成，注入日志上下文）
阶段二：/metrics Prometheus 文本格式指标端点（零第三方依赖，自实现暴露）

════════════════════════════════════════════════════════════════════
本模块的安全约束（改代码前请先读完）
════════════════════════════════════════════════════════════════════

1. 【日志注入】X-Request-ID 是**客户端可控输入**。写入日志前必须过
   「长度上限 64 + 字符白名单 [A-Za-z0-9._-]」。否则攻击者可注入 CRLF
   伪造日志行（混淆审计、伪造"谁做了什么"），或用超长字段撑爆日志与存储。
   → 见 sanitize_request_id()

2. 【指标端点未授权访问】/metrics 会暴露内部接口路径、调用量、延迟分布，
   属于内部情报。本实现：
     - 默认关闭（METRICS_ENABLED 未设即为关）
     - 开启后**强制令牌鉴权**，恒定时间比较（hmac.compare_digest）
     - 令牌未配置 → 一律拒绝（fail-closed），不依赖网络位置，
       也**不信任** X-Forwarded-For / X-Real-IP（经反向代理时这些头可伪造，
       且 nginx 作为 TCP 对端时 request.client 恒为 127.0.0.1，据此放行等于不设防）
   → 见 metrics_authorized()

3. 【埋点不得拖垮业务】本模块是旁路。自身任何异常都必须被吞掉并降级，
   绝不能因为埋点失败让业务请求返回 500。下游（业务）异常**不吞**，
   照常向上抛给应用自己的异常处理器。

4. 【指标标签基数爆炸 + 响应体注入】URL 路径会作为标签输出。必须做
   「字符集收敛 + 不同路径数上限（默认 400）」双重限制，否则攻击者用
   随机 URL 刷请求就能撑爆内存（基数 DoS），或把任意文本注入 /metrics 响应体。
   → 见 normalize_route() / MetricsRegistry._route_label()

5. 【多进程记账】uvicorn workers>1 时每个 worker 独立记账，同一指标名+标签
   若来自不同进程会产生相互矛盾的样本。故**所有指标都带 pid 标签**做区分。
   全局速率请用 PromQL 聚合，例如：
       sum by (method, route, status) (rate(aipm_http_requests_total[5m]))

阶段三（OTel 链路追踪）本轮不实现：需先选定后端与采样策略，属独立立项。
"""

import hmac
import logging
import os
import re
import threading
import time
import uuid
from contextvars import ContextVar
from typing import Dict, List, Optional, Tuple

from fastapi import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

LOG = logging.getLogger("app.core.observability")


# ══════════════════════════════════════════════════════════════════
# 阶段一：X-Request-ID 请求关联
# ══════════════════════════════════════════════════════════════════

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_HEADER_LC = b"x-request-id"

# 请求 ID 在 scope["state"] 中的键（供 request.state 使用）
REQUEST_ID_STATE_KEY = "request_id"

# 长度上限：超过即视为不合法（拒绝采用客户端值，改由服务端生成）
MAX_REQUEST_ID_LEN = 64

# 字符白名单：大小写字母、数字、点、下划线、连字符。
# 刻意排除：空白/CR/LF（日志注入）、引号、反斜杠、控制字符、非 ASCII（终端转义序列）。
_SAFE_REQUEST_ID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,64}\Z")

# 当前请求的 ID（contextvars：异步安全，跨请求/跨协程互不污染）
_request_id_ctx: ContextVar[str] = ContextVar("aipm_request_id", default="-")


def generate_request_id() -> str:
    """生成新的请求 ID（32 位十六进制，无连字符）。

    注意：不要用 uuid.UUID(...) 强转客户端传入值 —— 那是校验逻辑，不是生成逻辑，
    且对非法输入抛异常。生成侧永远用 uuid4().hex。
    """
    return uuid.uuid4().hex


def sanitize_request_id(raw: Optional[str]) -> Optional[str]:
    """把客户端提供的 X-Request-ID 规整为可安全写入日志/响应头的值。

    返回 None 表示「客户端值不可用」，调用方应改用 generate_request_id()。

    防御点：
      - CRLF / 换行 / 制表符 → 字符白名单直接拒绝（不被 .strip() 洗白后放过）
      - 超长字段 → 超过 64 即拒绝，不截断（截断会让攻击者构造的前缀进日志）
      - 控制字符、ANSI 转义序列、非 ASCII → 白名单拒绝
    """
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    if len(candidate) > MAX_REQUEST_ID_LEN:
        return None
    if not _SAFE_REQUEST_ID_RE.match(candidate):
        return None
    return candidate


def current_request_id() -> str:
    """取当前请求上下文中的 request id（非请求上下文返回 '-'）。"""
    try:
        return _request_id_ctx.get() or "-"
    except Exception:  # pragma: no cover - 防御性
        return "-"


def _header_from_scope(scope: Scope, lower_name: bytes) -> Optional[str]:
    """从 ASGI scope 的 headers 里取首个匹配的头（大小写不敏感）。"""
    try:
        headers = scope.get("headers") or []
    except Exception:
        return None
    try:
        for key, value in headers:
            if isinstance(key, bytes) and key.lower() == lower_name:
                return value.decode("latin-1") if isinstance(value, bytes) else str(value)
    except Exception:
        return None
    return None


# ── 日志上下文注入（LogRecord 工厂，全局生效，无需逐个 handler 挂 filter）──

_log_factory_installed = False


def install_request_id_logging() -> None:
    """幂等地安装 LogRecord 工厂，使**所有**日志记录都带 request_id 属性。

    用 LogRecordFactory 而不是 per-handler Filter 的原因：
    任何第三方库/后续新增的 handler 都能安全使用 %(request_id)s，不会 KeyError。
    """
    global _log_factory_installed
    if _log_factory_installed:
        return

    prev_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = prev_factory(*args, **kwargs)
        try:
            rid = _request_id_ctx.get()
        except Exception:
            rid = "-"
        try:
            if not getattr(record, "request_id", None):
                record.request_id = rid or "-"
        except Exception:
            pass
        return record

    logging.setLogRecordFactory(record_factory)
    _log_factory_installed = True


# ══════════════════════════════════════════════════════════════════
# 阶段二：Prometheus 指标（零依赖，自实现文本格式）
# ══════════════════════════════════════════════════════════════════

# 耗时直方图桶（毫秒），末桶 +Inf
_DURATION_BUCKETS_MS: Tuple[float, ...] = (
    5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, float("inf"),
)

# 折叠桶：路径基数超限时统一归入此标签
_OTHER_ROUTE = "__other__"

# 单个进程内允许的不同路径标签数上限（超出即折叠，防基数 DoS）
_MAX_ROUTE_SERIES = 400

_MAX_PATH_SEGMENTS = 12
_MAX_SEGMENT_LEN = 40
_MAX_PATH_LEN = 200

_SEGMENT_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._\-]")
_UUID_SEG_RE = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
_DIGITS_SEG_RE = re.compile(r"\A[0-9]{1,32}\Z")
_HEX_LONG_SEG_RE = re.compile(r"\A[0-9a-fA-F]{16,}\Z")


def normalize_route(path: str) -> str:
    """把 URL 路径收敛成「低基数 + 只含安全字符」的标签值。

    三重作用：
      1. 降基数：数字段/UUID 段/长十六进制段 → {id}/{uuid}，避免 object id 造成基数爆炸
      2. 防注入：非白名单字符统一替换为 '_'，换行/引号等无法进入 /metrics 响应体
      3. 限长：路径限 200 字符、最多 12 段、每段限 40 字符
    """
    try:
        if not isinstance(path, str) or not path:
            return "/"
        # 去掉 query / fragment（path 本身不应含，但恶意 scope 可能构造）
        path = path.split("?", 1)[0].split("#", 1)[0]
        if not path.startswith("/"):
            path = "/" + path
        if len(path) > _MAX_PATH_LEN:
            path = path[:_MAX_PATH_LEN]

        out: List[str] = []
        for seg in path.split("/")[: _MAX_PATH_SEGMENTS + 1]:
            if seg == "":
                out.append("")
                continue
            if _UUID_SEG_RE.match(seg):
                out.append("{uuid}")
            elif _DIGITS_SEG_RE.match(seg):
                out.append("{id}")
            elif _HEX_LONG_SEG_RE.match(seg):
                out.append("{id}")
            else:
                cleaned = _SEGMENT_UNSAFE_RE.sub("_", seg)
                if len(cleaned) > _MAX_SEGMENT_LEN:
                    cleaned = cleaned[:_MAX_SEGMENT_LEN]
                out.append(cleaned)

        result = "/".join(out)
        return result or "/"
    except Exception:
        return _OTHER_ROUTE


def _esc(value: object) -> str:
    """Prometheus 标签值转义（第二道防线；第一道是 normalize_route 的字符集收敛）。"""
    s = str(value)
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return s


def _fmt(value: object) -> str:
    """数值格式化：整数不带小数点，浮点保留 6 位。"""
    try:
        f = float(value)
    except Exception:
        return "0"
    if f != f or f in (float("inf"), float("-inf")):  # NaN / Inf
        return "0"
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return "%.6f" % f


class MetricsRegistry:
    """进程内指标注册表（线程安全：同步路由会跑在线程池里）。"""

    def __init__(self, max_routes: int = _MAX_ROUTE_SERIES) -> None:
        self._lock = threading.Lock()
        self._started = time.monotonic()
        self._max_routes = max_routes
        self._routes = {_OTHER_ROUTE}
        self._requests: Dict[Tuple[str, str, str], int] = {}
        # key -> [各桶计数, 耗时总和, 样本数]
        self._hist: Dict[Tuple[str, str], List[object]] = {}
        self._in_flight = 0
        self._cardinality_limited = 0
        self._errors = 0

    # ── 采集 ──

    def _route_label(self, route: str) -> str:
        if route in self._routes:
            return route
        if len(self._routes) < self._max_routes:
            self._routes.add(route)
            return route
        self._cardinality_limited += 1
        return _OTHER_ROUTE

    def begin(self) -> None:
        try:
            with self._lock:
                self._in_flight += 1
        except Exception:
            self.note_error()

    def end(self) -> None:
        """请求结束但未记录样本时的兜底（如连接中断）。"""
        try:
            with self._lock:
                if self._in_flight > 0:
                    self._in_flight -= 1
        except Exception:
            pass

    def finish(self, method: str, route: str, status: object, duration_ms: float) -> None:
        try:
            with self._lock:
                if self._in_flight > 0:
                    self._in_flight -= 1

                m = (str(method) or "-").upper()
                r = self._route_label(str(route) or _OTHER_ROUTE)
                try:
                    s = str(int(status))
                except Exception:
                    s = "0"

                rkey = (m, r, s)
                self._requests[rkey] = self._requests.get(rkey, 0) + 1

                hkey = (m, r)
                entry = self._hist.get(hkey)
                if entry is None:
                    entry = [[0] * len(_DURATION_BUCKETS_MS), 0.0, 0]
                    self._hist[hkey] = entry

                try:
                    d = float(duration_ms)
                except Exception:
                    d = 0.0
                if d < 0 or d != d:
                    d = 0.0

                counts = entry[0]
                for idx, le in enumerate(_DURATION_BUCKETS_MS):
                    if d <= le:
                        counts[idx] = counts[idx] + 1
                entry[1] = float(entry[1]) + d
                entry[2] = int(entry[2]) + 1
        except Exception:
            self.note_error()

    def note_error(self) -> None:
        """记录一次埋点自身异常（该计数应恒为 0，非 0 说明埋点有问题）。"""
        try:
            with self._lock:
                self._errors += 1
        except Exception:
            pass

    # ── 暴露 ──

    def render(self) -> str:
        pid = str(os.getpid())
        with self._lock:
            req_snap = list(self._requests.items())
            hist_snap = [(k, list(v[0]), float(v[1]), int(v[2])) for k, v in self._hist.items()]
            in_flight = self._in_flight
            limited = self._cardinality_limited
            errors = self._errors
        uptime = max(0.0, time.monotonic() - self._started)

        lines: List[str] = []

        lines.append(
            "# HELP aipm_http_requests_total HTTP 请求累计数"
            "（按 worker 进程独立记账，全局速率请 sum by(...) 聚合）"
        )
        lines.append("# TYPE aipm_http_requests_total counter")
        for (method, route, status), value in sorted(req_snap):
            labels = 'method="%s",route="%s",status="%s",pid="%s"' % (
                _esc(method), _esc(route), _esc(status), pid,
            )
            lines.append("aipm_http_requests_total{%s} %s" % (labels, _fmt(value)))

        lines.append("# HELP aipm_http_request_duration_ms HTTP 请求处理耗时直方图（毫秒）")
        lines.append("# TYPE aipm_http_request_duration_ms histogram")
        for (method, route), counts, dsum, dcount in sorted(hist_snap):
            for idx, le in enumerate(_DURATION_BUCKETS_MS):
                le_str = "+Inf" if le == float("inf") else ("%g" % le)
                labels = 'method="%s",route="%s",le="%s",pid="%s"' % (
                    _esc(method), _esc(route), le_str, pid,
                )
                lines.append("aipm_http_request_duration_ms_bucket{%s} %s" % (labels, _fmt(counts[idx])))
            labels = 'method="%s",route="%s",pid="%s"' % (_esc(method), _esc(route), pid)
            lines.append("aipm_http_request_duration_ms_sum{%s} %s" % (labels, _fmt(dsum)))
            lines.append("aipm_http_request_duration_ms_count{%s} %s" % (labels, _fmt(dcount)))

        lines.append("# HELP aipm_http_requests_in_flight 当前正在处理的请求数")
        lines.append("# TYPE aipm_http_requests_in_flight gauge")
        lines.append('aipm_http_requests_in_flight{pid="%s"} %s' % (pid, _fmt(in_flight)))

        lines.append("# HELP aipm_process_uptime_seconds worker 进程已运行秒数")
        lines.append("# TYPE aipm_process_uptime_seconds gauge")
        lines.append('aipm_process_uptime_seconds{pid="%s"} %s' % (pid, _fmt(uptime)))

        lines.append("# HELP aipm_metrics_cardinality_limited_total 因路径标签基数超限被折叠的样本数")
        lines.append("# TYPE aipm_metrics_cardinality_limited_total counter")
        lines.append('aipm_metrics_cardinality_limited_total{pid="%s"} %s' % (pid, _fmt(limited)))

        lines.append("# HELP aipm_observability_errors_total 埋点自身异常次数（正常应恒为 0）")
        lines.append("# TYPE aipm_observability_errors_total counter")
        lines.append('aipm_observability_errors_total{pid="%s"} %s' % (pid, _fmt(errors)))

        return "\n".join(lines) + "\n"


# 进程级单例
METRICS = MetricsRegistry()


# ══════════════════════════════════════════════════════════════════
# /metrics 访问控制
# ══════════════════════════════════════════════════════════════════

_TRUTHY = ("1", "true", "yes", "on")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def metrics_enabled() -> bool:
    """端点总开关。默认关闭 —— 未显式开启即不可访问。

    优先读 Settings（.env 与进程环境变量均由 pydantic-settings 统一装载，
    与项目其余配置一致）；字段缺失时回退直读环境变量。
    """
    v = getattr(settings, "METRICS_ENABLED", None)
    if v is None:
        return _env_flag("METRICS_ENABLED", False)
    return bool(v)


def configured_token() -> str:
    raw = getattr(settings, "METRICS_TOKEN", None)
    if raw is None:
        raw = os.environ.get("METRICS_TOKEN") or ""
    return str(raw).strip()


def _supplied_token(scope: Scope) -> Optional[str]:
    """从 Authorization: Bearer <t> 或 X-Metrics-Token: <t> 取令牌。"""
    try:
        headers = scope.get("headers") or []
    except Exception:
        return None
    try:
        for key, value in headers:
            if not isinstance(key, bytes):
                continue
            lk = key.lower()
            raw = value.decode("latin-1") if isinstance(value, bytes) else str(value)
            if lk == b"x-metrics-token":
                return raw.strip()
            if lk == b"authorization":
                token = raw.strip()
                if token[:7].lower() == "bearer ":
                    return token[7:].strip()
                return token
    except Exception:
        return None
    return None


def metrics_authorized(scope: Scope) -> bool:
    """判定 /metrics 访问是否授权。

    fail-closed：
      - 总开关未开  → 拒绝
      - 未配置令牌  → 拒绝（避免"配了端点忘了配令牌"导致裸奔）
      - 令牌不匹配  → 拒绝（恒定时间比较，防时序侧信道）
    不读取任何代理头判断来源 IP：经 nginx 时它们可伪造，且 TCP 对端恒为 127.0.0.1。
    """
    if not metrics_enabled():
        return False
    expected = configured_token()
    if not expected:
        return False
    supplied = _supplied_token(scope)
    if not supplied:
        return False
    try:
        return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))
    except Exception:
        return False


def install_metrics_route(app) -> None:
    """注册受保护的 /metrics 端点。

    未授权一律 403（不用 404：serve.py 的 SPA fallback 会把 404 的 GET 重写成
    index.html 200，会造成"到底有没有拦住"的误判）。
    """

    def _denied(reason: str) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "forbidden", "detail": reason},
            headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"},
        )

    @app.get("/metrics", include_in_schema=False)
    async def metrics_view(request: Request):
        try:
            if not metrics_enabled():
                return _denied("metrics endpoint disabled")
            if not configured_token():
                return _denied("metrics token not configured")
            if not metrics_authorized(request.scope):
                return _denied("invalid or missing metrics token")
            return PlainTextResponse(
                METRICS.render(),
                headers={
                    # Content-Type 必须用显式 headers 给出：media_type= 会让 starlette
                    # 0.33-0.35（FastAPI 0.109 锁定区间）对 text/* 无条件再追加 charset，
                    # 与规范值中的 charset 重复后，真实 Prometheus（Go mime.ParseMediaType
                    # 对重复参数报错）会拒收抓取
                    "Content-Type": "text/plain; version=0.0.4; charset=utf-8",
                    "Cache-Control": "no-store",
                },
            )
        except Exception:
            # 渲染失败也不暴露任何内部信息
            LOG.exception("渲染 /metrics 失败")
            return JSONResponse(
                status_code=500,
                content={"code": 500, "message": "metrics render failed"},
                headers={"Cache-Control": "no-store"},
            )

    return None


# ══════════════════════════════════════════════════════════════════
# 中间件：请求关联 + 指标采集（旁路，失败即降级）
# ══════════════════════════════════════════════════════════════════

class ObservabilityMiddleware:
    """纯 ASGI 中间件（不用 BaseHTTPMiddleware：避免其流式/异常语义带来的副作用）。

    职责：
      1. 确定 X-Request-ID（客户端有且合法则透传，否则服务端生成）
      2. 写入 contextvars → 本次请求内所有日志自动带 [rid=...]
      3. 写入响应头 X-Request-ID（便于前端/网关串联）
      4. 采集请求计数与耗时直方图

    降级：所有埋点逻辑独立 try/except，任何异常都只记 _errors，不影响请求本身。
    下游业务异常照常抛出，交给应用自己的异常处理器。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # ── 1. 确定 request id（失败则现生成一个，绝不影响请求）──
        try:
            incoming = _header_from_scope(scope, _REQUEST_ID_HEADER_LC)
            rid = sanitize_request_id(incoming) or generate_request_id()
        except Exception:
            rid = generate_request_id()

        # ctx.set 理论上不会抛，但仍兜住：它若失败，绝不能连累请求
        token = None
        try:
            token = _request_id_ctx.set(rid)
        except Exception:
            token = None
        finished = False

        # 供 request.state.request_id 使用
        try:
            state = scope.get("state")
            if not isinstance(state, dict):
                state = {}
                scope["state"] = state
            state[REQUEST_ID_STATE_KEY] = rid
        except Exception:
            pass

        started = time.perf_counter()
        # 埋点一律旁路：begin() 若抛异常，只记自监控计数，不能让请求失败
        try:
            METRICS.begin()
        except Exception:
            METRICS.note_error()

        async def send_wrapper(message: Message) -> None:
            nonlocal finished
            if message.get("type") == "http.response.start":
                # ── 3. 回写响应头（值为已规整的安全值，杜绝响应头注入）──
                try:
                    headers = message.setdefault("headers", [])
                    if isinstance(headers, list):
                        headers.append(
                            (REQUEST_ID_HEADER.encode("latin-1"), rid.encode("latin-1"))
                        )
                except Exception:
                    METRICS.note_error()

                # ── 4. 采集指标 ──
                if not finished:
                    finished = True
                    try:
                        status = message.get("status", 0) or 0
                        duration_ms = (time.perf_counter() - started) * 1000.0
                        route = normalize_route(scope.get("path", "") or "")
                        method = scope.get("method", "") or ""
                        METRICS.finish(method, route, status, duration_ms)
                    except Exception:
                        METRICS.note_error()
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if not finished:
                try:
                    METRICS.end()
                except Exception:
                    pass
            if token is not None:
                try:
                    _request_id_ctx.reset(token)
                except Exception:
                    pass

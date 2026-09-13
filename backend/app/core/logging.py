"""
PMI中国AI项目管理社区 - 日志配置

扩展（与 app/core/observability.py 配合）：
- 所有日志注入 request_id 字段（来自 X-Request-ID 中间件的 contextvar），
  便于把同一请求的访问日志/错误日志/慢查询日志串联起来
- LOG_JSON=true 时输出结构化 JSON 日志（每行一个 JSON 对象），
  便于 Loki/ELK 等日志平台直接采集解析
"""

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings
from app.core.observability import request_id_var

# 日志目录
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# 日志格式（文本模式；request_id 由 RequestIdFilter 注入，无请求上下文时为 "-"）
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s [%(request_id)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class RequestIdFilter(logging.Filter):
    """把当前请求的 request_id 注入每条日志记录。

    若记录已带 request_id（如经 logging extra 显式传入），优先沿用——
    用于未处理异常的兜底 handler：异常穿过中间件后 contextvar 已被 reset，
    但 request.state.request_id 仍在（见 main.py/serve.py 的 general handler）。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", None) or request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """结构化 JSON 日志格式（LOG_JSON=true 时启用）"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, DATE_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _make_formatter() -> logging.Formatter:
    return JsonFormatter(DATE_FORMAT) if settings.LOG_JSON else logging.Formatter(LOG_FORMAT, DATE_FORMAT)


def setup_logging():
    """设置日志配置"""
    # 根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    # 清除现有处理器
    root_logger.handlers.clear()

    # request_id 过滤器：挂在各 handler 上（logger 级 filter 不作用于 propagate 上来的
    # 记录），对所有经 root handler 输出的日志生效
    rid_filter = RequestIdFilter()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL))
    console_handler.setFormatter(_make_formatter())
    console_handler.addFilter(rid_filter)
    root_logger.addHandler(console_handler)

    # 文件处理器
    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding="utf-8"
    )
    file_handler.setLevel(getattr(logging, settings.LOG_LEVEL))
    file_handler.setFormatter(_make_formatter())
    file_handler.addFilter(rid_filter)
    root_logger.addHandler(file_handler)

    # 错误日志处理器
    error_handler = RotatingFileHandler(
        LOG_DIR / "error.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(_make_formatter())
    error_handler.addFilter(rid_filter)
    root_logger.addHandler(error_handler)

    # SQLAlchemy日志
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Uvicorn日志
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    return root_logger


# 创建logger实例
logger = logging.getLogger(__name__)

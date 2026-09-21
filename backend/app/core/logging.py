"""
PMI中国AI项目管理社区 - 日志配置
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import settings

# ── 请求关联（Issue #19 阶段一）──
# 守卫式导入：万一可观测性模块不可用，日志退化为原格式，绝不让应用起不来。
try:
    from app.core.observability import install_request_id_logging
except Exception:  # pragma: no cover
    install_request_id_logging = None

_PLAIN_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 日志目录
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# 日志格式
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [rid=%(request_id)s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging():
    """设置日志配置"""
    # 注入 request_id（幂等）。失败则退化为不含 rid 的格式，
    # 否则 %(request_id)s 会让每一条日志抛 KeyError。
    log_format = LOG_FORMAT
    if install_request_id_logging is not None:
        try:
            install_request_id_logging()
        except Exception:
            log_format = _PLAIN_LOG_FORMAT

    # 根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))
    
    # 清除现有处理器
    root_logger.handlers.clear()
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL))
    console_formatter = logging.Formatter(log_format, DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # 文件处理器
    file_handler = RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding="utf-8"
    )
    file_handler.setLevel(getattr(logging, settings.LOG_LEVEL))
    file_formatter = logging.Formatter(log_format, DATE_FORMAT)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # 错误日志处理器
    error_handler = RotatingFileHandler(
        LOG_DIR / "error.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(log_format, DATE_FORMAT)
    error_handler.setFormatter(error_formatter)
    root_logger.addHandler(error_handler)
    
    # SQLAlchemy日志
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    # Uvicorn日志
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    
    return root_logger


# 创建logger实例
logger = logging.getLogger(__name__)

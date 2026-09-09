"""
兼容入口 - ai_engine 已重构为包结构
原 from app.core.ai_engine import ai_engine 仍然可用（通过 ai_engine/__init__.py）
文件保留作为兼容提示
"""

from app.core.ai_engine import *  # noqa: F401, F403

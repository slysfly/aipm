"""
兼容入口 - agent_engine 已重构为包结构
原 from app.services.ai.agent_engine import agent_engine 仍然可用（通过 agent_engine/__init__.py）
文件保留作为兼容入口
"""

from app.services.ai.agent_engine import *  # noqa: F401, F403

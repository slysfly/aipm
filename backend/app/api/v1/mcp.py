"""
兼容入口 - mcp 已重构为 mcp_routes 包结构
原 from app.api.v1 import mcp 和 mcp.router 仍然可用（通过 mcp_routes 重新导出）
文件保留作为兼容入口
"""

from app.api.v1.mcp_routes import router  # noqa: F401

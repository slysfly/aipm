"""
PMI中国AI项目管理社区 - MCP (Model Context Protocol) API路由
提供MCP标准接口端点

[PMBOK KA: 跨领域 (Cross-area) — MCP协议、AI工具集成]
对应PMI第6版标准：MCP协议

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: AI Management — MCP协议模型集成]
PMBOK 7th Principle: Tailoring | Domain: Development Approach — 裁剪集成方法
PMBOK 8th: AI Integration Standard Protocol"""

import json
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.mcp_server import mcp_server, MCPError, MCPErrorCode
from app.api.v1.mcp_routes.tools import tools_router, register_tools
from app.api.v1.mcp_routes.resources import resources_router, register_resources
from app.api.v1.mcp_routes.prompts import prompts_router, register_prompts


class MCPInitializeRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = "init-1"
    method: str = "initialize"
    params: Dict[str, Any] = Field(default_factory=dict)


router = APIRouter(prefix="/mcp", tags=["MCP协议"])

# 包含子路由（子路由的路径会附加到主路由前缀 /mcp 后面）
router.include_router(tools_router)
router.include_router(resources_router)
router.include_router(prompts_router)


# ============ 注册所有 MCP 组件 ============

def register_mcp_components():
    """注册所有MCP组件（工具、资源、提示模板）"""
    register_tools()
    register_resources()
    register_prompts()


# 在模块加载时注册
register_mcp_components()
# 自动初始化，使 Web 端（无标准 MCP 握手）可直接列举/调用工具与资源
mcp_server.initialize()


# ============ 共享 API 端点 ============

@router.post("/initialize")
async def mcp_initialize(request: MCPInitializeRequest):
    try:
        result = mcp_server.initialize(request.params.get("capabilities"))
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "result": result,
        }
    except MCPError as e:
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {"code": e.code.value, "message": e.message, "data": e.data},
        }


@router.get("/sse")
async def mcp_sse_stream(request: Request):
    async def event_stream():
        endpoint = request.query_params.get("endpoint", "initialize")
        data_str = request.query_params.get("data", "{}")
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            data = {}

        async for event in mcp_server.sse_stream(endpoint, data):
            yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/status")
async def mcp_status():
    return {
        "status": "running",
        "protocol_version": mcp_server._protocol_version,
        "server_info": mcp_server._server_info,
        "capabilities": mcp_server._capabilities,
        "tools_count": len(mcp_server._tools),
        "resources_count": len(mcp_server._resources),
        "prompts_count": len(mcp_server._prompts),
    }

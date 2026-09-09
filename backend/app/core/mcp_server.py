"""
PMI中国AI项目管理社区 - MCP (Model Context Protocol) Server 实现
遵循 MCP 2024-11-05 标准规范
"""

import json
import asyncio
from typing import Dict, Any, List, Optional, Callable, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.core.ai_engine import ai_engine
from app.config import settings


class MCPErrorCode(Enum):
    """MCP标准错误码"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    SERVER_NOT_INITIALIZED = -32002
    UNKNOWN_TOOL = -32601
    UNKNOWN_RESOURCE = -32601
    UNKNOWN_PROMPT = -32601


class MCPError(Exception):
    """MCP错误"""
    def __init__(self, code: MCPErrorCode, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


@dataclass
class MCPTool:
    """MCP工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]


@dataclass
class MCPResource:
    """MCP资源定义"""
    uri: str
    name: str
    description: str
    mime_type: str
    handler: Callable[..., Any]


@dataclass
class MCPPrompt:
    """MCP提示模板定义"""
    name: str
    description: str
    arguments: List[Dict[str, Any]]
    handler: Callable[..., Any]


@dataclass
class MCPMessage:
    """Agent间通信消息"""
    id: str
    sender: str
    receiver: str
    content: str
    message_type: str = "text"
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MCPMessageQueue:
    """Agent间消息队列"""
    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._history: List[MCPMessage] = []

    def register_agent(self, agent_name: str):
        """注册Agent队列"""
        if agent_name not in self._queues:
            self._queues[agent_name] = asyncio.Queue()

    async def send(self, message: MCPMessage):
        """发送消息到目标Agent"""
        self._history.append(message)
        if message.receiver in self._queues:
            await self._queues[message.receiver].put(message)

    async def receive(self, agent_name: str, timeout: float = 30.0) -> Optional[MCPMessage]:
        """接收消息"""
        if agent_name not in self._queues:
            return None
        try:
            return await asyncio.wait_for(self._queues[agent_name].get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def get_history(self, agent_name: Optional[str] = None) -> List[MCPMessage]:
        """获取消息历史"""
        if agent_name:
            return [m for m in self._history if m.sender == agent_name or m.receiver == agent_name]
        return self._history.copy()

    def clear_history(self):
        """清空历史"""
        self._history.clear()


class MCPServer:
    """
    MCP Server 核心实现
    提供工具、资源、提示模板的标准化管理
    """

    def __init__(self):
        self._tools: Dict[str, MCPTool] = {}
        self._resources: Dict[str, MCPResource] = {}
        self._prompts: Dict[str, MCPPrompt] = {}
        self._message_queue = MCPMessageQueue()
        self._initialized = False
        self._protocol_version = "2024-11-05"
        self._server_info = {
            "name": "tw-ai-pms-mcp-server",
            "version": settings.VERSION,
        }
        self._capabilities = {
            "tools": {"listChanged": True},
            "resources": {"subscribe": True, "listChanged": True},
            "prompts": {"listChanged": True},
            "logging": {},
        }

    # ============ 生命周期管理 ============

    def initialize(self, client_capabilities: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """初始化MCP连接"""
        self._initialized = True
        return {
            "protocolVersion": self._protocol_version,
            "capabilities": self._capabilities,
            "serverInfo": self._server_info,
        }

    def check_initialized(self):
        """检查是否已初始化"""
        if not self._initialized:
            raise MCPError(MCPErrorCode.SERVER_NOT_INITIALIZED, "Server not initialized")

    # ============ 工具管理 ============

    def register_tool(self, tool: MCPTool):
        """注册工具"""
        self._tools[tool.name] = tool

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有可用工具"""
        self.check_initialized()
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用工具"""
        self.check_initialized()
        if name not in self._tools:
            raise MCPError(MCPErrorCode.UNKNOWN_TOOL, f"Unknown tool: {name}")

        tool = self._tools[name]
        try:
            result = await tool.handler(**arguments)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, default=str),
                    }
                ],
                "isError": False,
            }
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Tool execution error: {str(e)}",
                    }
                ],
                "isError": True,
            }

    # ============ 资源管理 ============

    def register_resource(self, resource: MCPResource):
        """注册资源"""
        self._resources[resource.uri] = resource

    def list_resources(self) -> List[Dict[str, Any]]:
        """列出所有可用资源"""
        self.check_initialized()
        return [
            {
                "uri": resource.uri,
                "name": resource.name,
                "description": resource.description,
                "mimeType": resource.mime_type,
            }
            for resource in self._resources.values()
        ]

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """读取资源"""
        self.check_initialized()
        if uri not in self._resources:
            raise MCPError(MCPErrorCode.UNKNOWN_RESOURCE, f"Unknown resource: {uri}")

        resource = self._resources[uri]
        try:
            content = await resource.handler()
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": resource.mime_type,
                        "text": json.dumps(content, ensure_ascii=False, default=str),
                    }
                ]
            }
        except Exception as e:
            raise MCPError(MCPErrorCode.INTERNAL_ERROR, f"Resource read error: {str(e)}")

    # ============ 提示模板管理 ============

    def register_prompt(self, prompt: MCPPrompt):
        """注册提示模板"""
        self._prompts[prompt.name] = prompt

    def list_prompts(self) -> List[Dict[str, Any]]:
        """列出所有可用提示模板"""
        self.check_initialized()
        return [
            {
                "name": prompt.name,
                "description": prompt.description,
                "arguments": prompt.arguments,
            }
            for prompt in self._prompts.values()
        ]

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取提示模板"""
        self.check_initialized()
        if name not in self._prompts:
            raise MCPError(MCPErrorCode.UNKNOWN_PROMPT, f"Unknown prompt: {name}")

        prompt = self._prompts[name]
        try:
            messages = await prompt.handler(**(arguments or {}))
            return {
                "description": prompt.description,
                "messages": messages,
            }
        except Exception as e:
            raise MCPError(MCPErrorCode.INTERNAL_ERROR, f"Prompt generation error: {str(e)}")

    # ============ 消息队列访问 ============

    @property
    def message_queue(self) -> MCPMessageQueue:
        """获取消息队列"""
        return self._message_queue

    # ============ SSE 流式支持 ============

    async def sse_stream(self, endpoint: str, data: Dict[str, Any]) -> AsyncIterator[str]:
        """SSE流式传输"""
        if endpoint == "initialize":
            result = self.initialize(data.get("capabilities"))
            yield f"event: initialize\ndata: {json.dumps(result)}\n\n"
        elif endpoint == "tools/list":
            tools = self.list_tools()
            yield f"event: tools/list\ndata: {json.dumps({'tools': tools})}\n\n"
        elif endpoint == "resources/list":
            resources = self.list_resources()
            yield f"event: resources/list\ndata: {json.dumps({'resources': resources})}\n\n"
        elif endpoint == "prompts/list":
            prompts = self.list_prompts()
            yield f"event: prompts/list\ndata: {json.dumps({'prompts': prompts})}\n\n"
        else:
            yield f"event: error\ndata: {json.dumps({'error': 'Unknown endpoint'})}\n\n"


# ============ 全局 MCP Server 实例 ============

mcp_server = MCPServer()

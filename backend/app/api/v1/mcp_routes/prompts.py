from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends
from app.core.security import get_current_active_user
from pydantic import BaseModel, Field

from app.core.mcp_server import mcp_server, MCPPrompt, MCPError, MCPErrorCode


prompts_router = APIRouter(dependencies=[Depends(get_current_active_user)])


class MCPPromptsListRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str = ""
    method: str = "prompts/list"
    params: Dict[str, Any] = Field(default_factory=dict)


class MCPPromptsGetRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str = ""
    method: str = "prompts/get"
    params: Dict[str, Any]


async def prompt_task_breakdown(project_name: str = "", project_description: str = "") -> List[Dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": "你是一位资深项目管理专家，擅长WBS工作分解结构。请根据项目信息生成详细的任务分解。",
        },
        {
            "role": "user",
            "content": f"请为以下项目生成WBS任务分解：\n\n项目名称：{project_name}\n项目描述：{project_description}\n\n要求：\n1. 至少分解到3级WBS\n2. 每个任务包含预估工期\n3. 识别任务间的依赖关系\n4. 标注关键路径",
        },
    ]


async def prompt_risk_analysis(project_name: str = "", project_context: str = "") -> List[Dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": "你是一位项目风险管理专家，擅长识别和评估项目风险。",
        },
        {
            "role": "user",
            "content": f"请分析以下项目的风险：\n\n项目名称：{project_name}\n项目背景：{project_context}\n\n要求：\n1. 识别至少5个潜在风险\n2. 评估每个风险的概率和影响\n3. 提供应对策略建议\n4. 按优先级排序",
        },
    ]


async def prompt_code_review(code: str = "", language: str = "python") -> List[Dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": "你是一位资深代码审查专家，擅长发现代码中的问题和改进点。",
        },
        {
            "role": "user",
            "content": f"请审查以下{language}代码：\n\n```{language}\n{code}\n```\n\n请从以下维度分析：\n1. 代码质量和可读性\n2. 潜在bug和安全问题\n3. 性能优化建议\n4. 最佳实践遵循情况",
        },
    ]


async def prompt_meeting_summary(meeting_transcript: str = "") -> List[Dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": "你是一位专业的会议记录员，擅长提取会议要点和跟踪行动项。",
        },
        {
            "role": "user",
            "content": f"请总结以下会议内容：\n\n{meeting_transcript}\n\n请输出：\n1. 会议主题和参与者\n2. 关键决策点\n3. 行动项（含负责人和截止日期）\n4. 待跟进事项",
        },
    ]


def register_prompts():
    """注册所有MCP提示模板"""
    mcp_server.register_prompt(MCPPrompt(
        name="task_breakdown",
        description="将项目分解为WBS任务结构",
        arguments=[
            {"name": "project_name", "description": "项目名称", "required": True},
            {"name": "project_description", "description": "项目描述", "required": False},
        ],
        handler=prompt_task_breakdown,
    ))

    mcp_server.register_prompt(MCPPrompt(
        name="risk_analysis",
        description="分析项目风险并提供应对策略",
        arguments=[
            {"name": "project_name", "description": "项目名称", "required": True},
            {"name": "project_context", "description": "项目背景信息", "required": False},
        ],
        handler=prompt_risk_analysis,
    ))

    mcp_server.register_prompt(MCPPrompt(
        name="code_review",
        description="审查代码质量和安全性",
        arguments=[
            {"name": "code", "description": "代码内容", "required": True},
            {"name": "language", "description": "编程语言", "required": False},
        ],
        handler=prompt_code_review,
    ))

    mcp_server.register_prompt(MCPPrompt(
        name="meeting_summary",
        description="总结会议内容并提取行动项",
        arguments=[
            {"name": "meeting_transcript", "description": "会议记录或转录文本", "required": True},
        ],
        handler=prompt_meeting_summary,
    ))


@prompts_router.post("/prompts/list")
async def mcp_prompts_list(request: MCPPromptsListRequest):
    try:
        prompts = mcp_server.list_prompts()
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "result": {"prompts": prompts},
        }
    except MCPError as e:
        return {
            "jsonrpc": "2.0",
            "id": request.id,
            "error": {"code": e.code.value, "message": e.message, "data": e.data},
        }


@prompts_router.post("/prompts/get")
async def mcp_prompts_get(request: MCPPromptsGetRequest):
    try:
        params = request.params
        name = params.get("name")
        arguments = params.get("arguments", {})

        if not name:
            raise MCPError(MCPErrorCode.INVALID_PARAMS, "Prompt name is required")

        result = await mcp_server.get_prompt(name, arguments)
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

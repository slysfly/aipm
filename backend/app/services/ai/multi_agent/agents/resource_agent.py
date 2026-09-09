"""
PMI中国AI项目管理社区 - 资源调度 Agent (Executor)
执行具体任务（创建任务、查询数据等），返回执行结果
"""

import json
from typing import Dict, Any, List, Optional

from ..helpers import BaseAgent, AgentRole, AgentPlan, AgentResult


class ExecutorAgent(BaseAgent):
    """
    执行者Agent
    执行具体的项目管理操作，如创建任务、更新状态、生成报告等
    """

    def __init__(self, llm_provider: Optional[str] = None):
        super().__init__(
            name="Executor",
            role=AgentRole.EXECUTOR,
            description="负责执行具体的项目管理操作，如创建任务、更新状态、生成报告等",
            tools=["create_task", "query_tasks", "update_task", "generate_report", "create_project"],
            llm_provider=llm_provider,
        )

    def _build_think_prompt(self, context: Dict[str, Any]) -> str:
        task = context.get("task", "")
        available_tools = context.get("available_tools", self.tools)

        return f"""你是一位项目执行专家。请分析以下任务并确定最佳执行方案。

任务：{task}

可用工具：{', '.join(available_tools)}

请输出JSON格式的执行计划：
{{
    "reasoning": "执行思路",
    "steps": [
        {{
            "action": "工具名称或操作",
            "parameters": {{}},
            "expected_result": "预期结果"
        }}
    ]
}}

只输出JSON，不要其他内容。"""

    def _parse_plan(self, response: str) -> AgentPlan:
        try:
            data = json.loads(response.strip().strip("`").strip("json").strip("`").strip())
            return AgentPlan(
                steps=data.get("steps", []),
                reasoning=data.get("reasoning", ""),
            )
        except json.JSONDecodeError:
            return AgentPlan(
                steps=[{"action": "execute_direct", "task": response}],
                reasoning="Direct execution",
            )

    async def _execute_step(self, step: Dict[str, Any]) -> AgentResult:
        from app.core.mcp_server import mcp_server
        from app.core.ai_engine import ai_engine

        action = step.get("action", "")
        parameters = step.get("parameters", {})

        # 调用MCP工具
        if action in ["create_task", "query_tasks", "update_task", "generate_report", "create_project"]:
            try:
                result = await mcp_server.call_tool(action, parameters)
                content = result.get("content", [{}])[0].get("text", "")
                return AgentResult(
                    success=not result.get("isError", False),
                    data=json.loads(content) if content else {},
                    message=f"Tool {action} executed",
                )
            except Exception as e:
                return AgentResult(success=False, message=str(e))

        # 使用LLM直接处理
        if action in ["execute_direct", "ai_chat"]:
            try:
                task = step.get("task", parameters.get("message", ""))
                response = await ai_engine.generate(
                    f"请执行以下任务并返回结果：\n\n{task}",
                    provider=self.llm_provider,
                    temperature=0.3,
                )
                return AgentResult(success=True, data={"response": response}, message="Direct execution completed")
            except Exception as e:
                return AgentResult(success=False, message=str(e))

        return AgentResult(success=False, message=f"Unknown action: {action}")

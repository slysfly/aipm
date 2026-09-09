"""
PMI中国AI项目管理社区 - 任务分解 Agent (Planner)
接收用户目标，分解为子任务，分配给合适的执行Agent
"""

import json
import uuid
from typing import Dict, Any, List, Optional

from ..helpers import (
    BaseAgent, AgentRole, AgentPlan, AgentResult, SubTask
)


class PlannerAgent(BaseAgent):
    """
    规划者Agent
    接收用户目标，分解为子任务，分配给合适的执行Agent
    """

    def __init__(self, llm_provider: Optional[str] = None):
        super().__init__(
            name="Planner",
            role=AgentRole.PLANNER,
            description="负责将用户目标分解为可执行的子任务，并制定执行策略",
            tools=["analyze_project", "ai_chat"],
            llm_provider=llm_provider,
        )

    def _build_think_prompt(self, context: Dict[str, Any]) -> str:
        objective = context.get("objective", "")
        available_agents = context.get("available_agents", [])
        constraints = context.get("constraints", {})

        agents_desc = "\n".join([
            f"- {a['name']} ({a['role']}): {a['description']}"
            for a in available_agents
        ])

        return f"""你是一位项目管理规划专家。请将以下目标分解为详细的执行计划。

用户目标：{objective}

可用Agent：
{agents_desc}

约束条件：{json.dumps(constraints, ensure_ascii=False)}

请输出JSON格式的计划：
{{
    "reasoning": "分解思路",
    "steps": [
        {{
            "id": "step-1",
            "action": "具体行动描述",
            "assigned_to": "Agent名称",
            "estimated_duration": 10,
            "dependencies": [],
            "input": {{}},
            "expected_output": "预期结果"
        }}
    ],
    "estimated_duration": 30
}}

要求：
1. 每个步骤明确指定执行Agent
2. 标注步骤间的依赖关系
3. 提供预估执行时间
4. 只输出JSON，不要其他内容"""

    def _parse_plan(self, response: str) -> AgentPlan:
        try:
            data = json.loads(response.strip().strip("`").strip("json").strip("`").strip())
            return AgentPlan(
                steps=data.get("steps", []),
                reasoning=data.get("reasoning", ""),
                estimated_duration=data.get("estimated_duration", 0),
                dependencies=[],
            )
        except json.JSONDecodeError:
            # 尝试从文本中提取JSON
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    return AgentPlan(
                        steps=data.get("steps", []),
                        reasoning=data.get("reasoning", ""),
                        estimated_duration=data.get("estimated_duration", 0),
                    )
                except json.JSONDecodeError:
                    pass
            return AgentPlan(
                steps=[{"action": "direct_execution", "input": response}],
                reasoning="Failed to parse structured plan, using direct execution",
            )

    async def _execute_step(self, step: Dict[str, Any]) -> AgentResult:
        # Planner主要负责规划，不直接执行操作
        return AgentResult(
            success=True,
            data=step,
            message=f"Plan step: {step.get('action', 'unknown')}",
        )

    async def decompose_objective(self, objective: str, available_agents: List[Dict[str, Any]]) -> List[SubTask]:
        """
        将目标分解为子任务
        """
        context = {
            "objective": objective,
            "available_agents": available_agents,
        }

        plan = await self.think(context)
        subtasks = []

        for step in plan.steps:
            subtask = SubTask(
                id=step.get("id", str(uuid.uuid4())),
                description=step.get("action", ""),
                assigned_to=step.get("assigned_to", "Executor"),
                dependencies=step.get("dependencies", []),
            )
            subtasks.append(subtask)

        self._log("decompose", f"目标已分解为 {len(subtasks)} 个子任务")
        return subtasks

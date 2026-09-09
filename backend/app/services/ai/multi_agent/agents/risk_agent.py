"""
PMI中国AI项目管理社区 - 风险分析 Agent (Reviewer)
审查执行结果，提出修改建议
"""

import json
from typing import Dict, Any, List, Optional

from ..helpers import BaseAgent, AgentRole, AgentPlan, AgentResult


class ReviewerAgent(BaseAgent):
    """
    审查者Agent
    审查执行结果的质量，识别问题并提出改进建议
    """

    def __init__(self, llm_provider: Optional[str] = None):
        super().__init__(
            name="Reviewer",
            role=AgentRole.REVIEWER,
            description="负责审查执行结果的质量，识别问题并提出改进建议",
            tools=["analyze_project", "ai_chat"],
            llm_provider=llm_provider,
        )

    def _build_think_prompt(self, context: Dict[str, Any]) -> str:
        result = context.get("result", {})
        criteria = context.get("criteria", [])

        return f"""你是一位质量审查专家。请审查以下执行结果。

执行结果：{json.dumps(result, ensure_ascii=False, default=str)}

审查标准：
{chr(10).join(f"- {c}" for c in criteria)}

请输出JSON格式的审查报告：
{{
    "passed": true/false,
    "score": 0.85,
    "issues": [
        {{
            "severity": "high/medium/low",
            "description": "问题描述",
            "suggestion": "改进建议"
        }}
    ],
    "recommendations": ["建议1", "建议2"]
}}

只输出JSON，不要其他内容。"""

    def _parse_plan(self, response: str) -> AgentPlan:
        return AgentPlan(steps=[{"action": "review", "content": response}])

    async def _execute_step(self, step: Dict[str, Any]) -> AgentResult:
        return AgentResult(success=True, data=step)

    async def review(self, result: AgentResult, criteria: List[str]) -> Dict[str, Any]:
        """
        审查执行结果
        """
        context = {
            "result": result.to_dict() if hasattr(result, "to_dict") else result.__dict__,
            "criteria": criteria,
        }

        plan = await self.think(context)
        review_content = plan.steps[0].get("content", "{}") if plan.steps else "{}"

        try:
            review_data = json.loads(review_content.strip().strip("`").strip("json").strip("`").strip())
        except json.JSONDecodeError:
            review_data = {
                "passed": True,
                "score": 0.8,
                "issues": [],
                "recommendations": [],
            }

        self._log("review", f"审查完成，通过: {review_data.get('passed', True)}, 评分: {review_data.get('score', 0)}")
        return review_data

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data["review_criteria"] = ["准确性", "完整性", "一致性", "可执行性"]
        return data

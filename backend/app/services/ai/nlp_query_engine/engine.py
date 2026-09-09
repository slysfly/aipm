"""
PMI中国AI项目管理社区 - AI自然语言查询执行引擎（NLP to SQL/API）
使用LLM将自然语言转换为结构化查询意图，并执行真实SQL查询

[CPMAI Phase: CPMAI Phase: Business Understanding | Domain: AI Fundamentals — NLP智能查询引擎]
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_engine import ai_engine
from app.models import Task, Project, User, Risk, Milestone, Comment
from . import parser as parser_mod
from . import executor as executor_mod


class NLPQueryEngine:
    """自然语言查询引擎：NLP -> 结构化查询计划 -> SQL执行 -> 自然语言摘要"""

    def __init__(self):
        self._entity_models = {
            "task": Task,
            "project": Project,
            "user": User,
            "risk": Risk,
            "milestone": Milestone,
            "comment": Comment,
        }

    async def parse_query(self, text: str) -> Dict[str, Any]:
        """
        解析自然语言查询为结构化查询意图
        使用LLM进行智能解析，失败时降级到规则解析
        """
        return await parser_mod.parse_query(self, text)

    async def execute_query(
        self,
        query_plan: Dict[str, Any],
        db: AsyncSession,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行结构化查询计划，返回真实数据库查询结果
        """
        return await executor_mod.execute_query(self, query_plan, db, project_id)

    async def generate_summary(self, results: Dict[str, Any], original_text: str) -> str:
        """
        使用LLM将查询结果转换为人类可读的自然语言摘要
        """
        data = results.get("data", [])
        total = results.get("total", 0)
        is_aggregate = results.get("is_aggregate", False)

        if not data:
            return f"未找到符合「{original_text}」条件的数据。"

        # 构建结果摘要上下文
        result_preview = json.dumps(data[:20], ensure_ascii=False, default=str)

        system_prompt = """你是一个数据分析助手。请根据用户的原始查询和查询结果，生成一段简洁、自然的中文摘要。

要求：
1. 直接回答用户的问题，不要重复查询条件
2. 使用自然、口语化的中文
3. 如果结果是聚合数据，总结关键数字和趋势
4. 如果结果是列表，说明总数和关键信息
5. 控制在100字以内
6. 不要提及技术细节（如SQL、数据库等）"""

        user_prompt = f"""用户查询：{original_text}

查询结果（共{total}条）：
{result_preview}

请生成一段自然语言摘要："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            summary = await ai_engine.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=300,
            )
            return summary.strip()
        except Exception:
            # 降级：生成简单摘要
            if is_aggregate:
                return f"查询完成，共获得 {total} 条聚合数据。"
            else:
                return f"查询完成，共找到 {total} 条符合条件的数据。"

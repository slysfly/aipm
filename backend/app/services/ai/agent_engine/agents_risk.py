"""
风险分析 Agent 模块
提供风险识别、评估和应对策略相关的Agent逻辑
"""

from typing import List, Dict, Any


# 风险分析提示模板
RISK_ANALYSIS_PROMPT = """你是一位项目风险管理专家，擅长识别和评估项目风险。
请分析以下项目的风险：

项目名称：{project_name}
项目背景：{project_context}

要求：
1. 识别至少5个潜在风险
2. 评估每个风险的概率和影响
3. 提供应对策略建议
4. 按优先级排序
"""


def calculate_risk_score(probability: float, impact: float) -> float:
    """计算风险得分 (P x I)"""
    return round(probability * impact, 2)


def get_risk_level(score: float) -> str:
    """根据风险得分确定风险等级"""
    if score >= 0.7:
        return "high"
    elif score >= 0.4:
        return "medium"
    else:
        return "low"

"""
PMI中国AI项目管理社区 - NLP查询引擎包
将自然语言转换为结构化查询并执行
"""

from app.services.ai.nlp_query_engine.engine import NLPQueryEngine

# 全局查询引擎实例（保持向后兼容）
nlp_query_engine = NLPQueryEngine()

__all__ = [
    "NLPQueryEngine",
    "nlp_query_engine",
]

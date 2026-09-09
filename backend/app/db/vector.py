"""向量列类型适配层。

目标：让 KnowledgeChunk.embedding 在两种引擎下都能工作，且 PostgreSQL 下
实现真正的向量最近邻检索（消灭 69k 行级别 O(N) 全表扫描 + Python 余弦）：

  - PostgreSQL -> pgvector.sqlalchemy.Vector(dim)，配合 cosine_distance 做 SQL 层 NN；
  - SQLite      -> JSON 列（向后兼容），检索走 Python 余弦降级。

维度由嵌入模型决定，默认 768（BAAI/bge-base-zh，与 config.RAG_LOCAL_MODEL 一致）。
若更换嵌入模型导致维度变化，须同步调整 RAG_EMBEDDING_DIM 并重建库。
"""
from sqlalchemy import JSON

from app.config import settings


def is_postgres() -> bool:
    """当前是否使用 PostgreSQL（pgvector 路径）。"""
    return "sqlite" not in settings.DATABASE_URL.lower()


# 常见嵌入模型 -> 维度映射；命中即采用，避免 pgvector 固定维度与模型不匹配。
_KNOWN_DIMS = {
    "bge-base-zh": 768,
    "bge-small-zh": 512,
    "bge-large-zh": 1024,
    "bge-m3": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def embedding_dim() -> int:
    """返回向量维度（优先显式 RAG_EMBEDDING_DIM，否则按模型名推断，兜底 768）。"""
    explicit = getattr(settings, "RAG_EMBEDDING_DIM", None)
    if explicit:
        try:
            return int(explicit)
        except Exception:
            pass
    model = (getattr(settings, "RAG_LOCAL_MODEL", "") or "BAAI/bge-base-zh").lower()
    for key, dim in _KNOWN_DIMS.items():
        if key in model:
            return dim
    return 768


def embedding_column():
    """返回 KnowledgeChunk.embedding 的列定义。

    PostgreSQL -> pgvector.sqlalchemy.Vector(dim)（要求目标库已 CREATE EXTENSION vector）；
    SQLite      -> JSON（向后兼容）。
    """
    if is_postgres():
        try:
            from pgvector.sqlalchemy import Vector
        except Exception as e:  # 缺依赖时给出明确错误，便于安装期修复
            raise RuntimeError(
                "当前为 PostgreSQL 但缺少 pgvector 依赖：请 `pip install pgvector` "
                "并确保目标库已执行 CREATE EXTENSION vector"
            ) from e
        return Vector(embedding_dim())
    return JSON()

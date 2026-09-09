"""
PMI中国AI项目管理社区 - 自动知识沉淀服务（AutoRAG）
机制：业务对象（项目/任务/风险/经验教训等）创建或更新时，自动抽取为知识文档与片段，
沉淀到"系统自动知识库"，供后续 AI 检索问答（复用 knowledge_base 的 RAG 接口）。

技术选型说明：采用轻量 AutoRAG（自动抽取 + 结构化分块 + 元数据标签），
不强制依赖向量库——优先使用各业务结构化字段作为检索元数据；
若后续启用 embedding，knowledge_chunks.embedding(JSON) 字段可直接复用升级为 GraphRAG/向量检索。
"""

import logging
from typing import Optional

from sqlalchemy import select

from app.models.knowledge_base import (
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeChunk,
    DocumentStatus,
    SourceType,
)
from app.models import User

logger = logging.getLogger("app.knowledge_auto")

SYSTEM_KB_NAME = "系统自动知识库"


async def ensure_system_kb(db, created_by: str) -> KnowledgeBase:
    """获取或创建系统默认知识库。"""
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.name == SYSTEM_KB_NAME))
    kb = result.scalar_one_or_none()
    if kb:
        return kb
    kb = KnowledgeBase(
        name=SYSTEM_KB_NAME,
        description="由系统自动沉淀的业务知识（项目/任务/风险/经验教训等），供 AI 检索问答。",
        created_by=created_by,
        embedding_model="none",
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return kb


def _chunk_text(text: str, size: int = 600):
    if not text:
        return []
    paras = [p for p in text.split("\n") if p.strip()]
    chunks: list = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) < size:
            buf += p + "\n"
        else:
            if buf:
                chunks.append(buf.strip())
            buf = p + "\n"
    if buf:
        chunks.append(buf.strip())
    return chunks or [text.strip()]


async def auto_ingest(
    db,
    kind: str,
    title: str,
    content: str,
    project_id: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Optional[str]:
    """将一条业务知识自动沉淀到系统知识库（best-effort，失败不影响主流程）。"""
    try:
        if not created_by:
            u = (await db.execute(select(User).limit(1))).scalar_one_or_none()
            created_by = u.id if u else "system"
        kb = await ensure_system_kb(db, created_by)
        doc = KnowledgeDocument(
            kb_id=kb.id,
            title=f"[{kind}] {title}",
            content=content.encode("utf-8"),
            source_type=SourceType.TEXT.value,
            status=DocumentStatus.COMPLETED.value,
            meta_data={"kind": kind, "project_id": project_id},
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        chunks = _chunk_text(content)
        for i, c in enumerate(chunks):
            db.add(
                KnowledgeChunk(
                    document_id=doc.id,
                    content=c,
                    chunk_index=i,
                    meta_data={"kind": kind, "project_id": project_id},
                )
            )
        doc.chunk_count = len(chunks)
        await db.commit()
        return doc.id
    except Exception as e:  # pragma: no cover
        logger.warning("自动知识沉淀失败（已忽略）: %s", e)
        return None

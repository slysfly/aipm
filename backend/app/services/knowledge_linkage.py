"""
PMI中国AI项目管理社区 - 数据闭环（组织过程资产 OPA）联动服务

把「经验教训(Lessons Learned)」自动沉淀为「知识库(Knowledge Base)」文档，
形成项目全生命周期的数据闭环：执行 -> 复盘 -> 知识 -> 复用。
已在知识库/复盘页面通过 API 触发。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase, KnowledgeDocument
from app.models.pm_extras import Lesson
from app.models import Project
from app.services.rag_engine import RAGEngine


def _lesson_to_content(lesson: Lesson) -> str:
    parts = [
        f"# {lesson.title}",
        f"所属项目：{lesson.project_name or '未指定'}",
        f"类别：{lesson.category}",
        f"评分：{lesson.rating}/5",
        "",
        f"## 背景\n{lesson.description or '（无）'}",
        f"## 做得好的地方\n{lesson.what_went_well or '（无）'}",
        f"## 待改进\n{lesson.what_could_improve or '（无）'}",
        f"## 行动项\n{lesson.action_items or '（无）'}",
    ]
    return "\n".join(parts)


async def _ensure_kb(db: AsyncSession, user_id: str, project_name: str) -> KnowledgeBase:
    """根据项目名找到项目并复用其知识库；否则使用/创建公司级 OPA 知识库。"""
    project = None
    if project_name:
        project = (await db.execute(
            select(Project).where(Project.name == project_name, Project.is_deleted == False)
        )).scalar_one_or_none()

    if project:
        kb = (await db.execute(
            select(KnowledgeBase).where(KnowledgeBase.project_id == project.id)
        )).scalar_one_or_none()
        if kb:
            return kb
        kb = KnowledgeBase(
            name=f"{project.name} · 知识库", description="项目知识沉淀（含经验教训）",
            project_id=project.id, created_by=user_id,
        )
        db.add(kb)
        await db.flush()
        return kb

    # 公司级 OPA 知识库
    kb = (await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.name == "组织过程资产(OPA)")
    )).scalar_one_or_none()
    if kb:
        return kb
    kb = KnowledgeBase(name="组织过程资产(OPA)", description="跨项目的经验教训与最佳实践沉淀", created_by=user_id)
    db.add(kb)
    await db.flush()
    return kb


async def archive_lesson_to_knowledge(
    db: AsyncSession, lesson_id: str, user_id: str
) -> Dict[str, Any]:
    lesson = await db.get(Lesson, lesson_id)
    if not lesson:
        raise ValueError("经验教训不存在")
    kb = await _ensure_kb(db, user_id, lesson.project_name)
    rag = RAGEngine(db_session=db)
    doc: KnowledgeDocument = await rag.add_document(
        kb_id=kb.id,
        title=f"[复盘] {lesson.title}",
        content=_lesson_to_content(lesson),
        source_type="text",
        meta_data={"source": "lesson_learned", "lesson_id": lesson.id, "category": lesson.category},
    )
    await db.commit()
    return {"kb_id": kb.id, "kb_name": kb.name, "doc_id": doc.id, "doc_title": doc.title}


async def archive_all_lessons(db: AsyncSession, user_id: str) -> Dict[str, Any]:
    lessons = (await db.execute(select(Lesson))).scalars().all()
    archived = []
    for lesson in lessons:
        try:
            r = await archive_lesson_to_knowledge(db, lesson.id, user_id)
            archived.append({"lesson_id": lesson.id, "doc_id": r["doc_id"]})
        except Exception:
            continue
    return {"total": len(lessons), "archived": len(archived), "items": archived}

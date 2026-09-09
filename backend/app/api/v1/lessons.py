"""
经验教训登记册 API (Lessons Learned)

[PMBOK KA: 跨领域 | PG: 收尾 (Cross-area/Closing) — 经验教训沉淀、项目复盘]
对应PMI第6版标准：经验教训沉淀、项目复盘

[CPMAI Phase: CPMAI Phase: Model Operationalization | Domain: CPMAI Methodology — 持续优化反馈]"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.pm_extras import Lesson
from app.models import User
from app.models.knowledge_base import KnowledgeBase as KBModel
from app.core.security import get_current_user, get_current_active_user
from app.services.knowledge_linkage import archive_lesson_to_knowledge, archive_all_lessons
from app.services.ai.out_of_box_agents import _llm, _safe_json
from app.services.rag_engine import get_rag_engine
from app.services.kb_access import get_accessible_kb_ids

router = APIRouter(prefix="/lessons", tags=["经验教训"], dependencies=[Depends(get_current_active_user)])


class LessonCreate(BaseModel):
    title: str
    projectName: str = ""
    category: str = "项目管理"
    description: str = ""
    whatWentWell: str = ""
    whatCouldImprove: str = ""
    actionItems: str = ""
    rating: int = 3
    createdBy: str = ""


class LessonUpdate(BaseModel):
    title: Optional[str] = None
    projectName: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    whatWentWell: Optional[str] = None
    whatCouldImprove: Optional[str] = None
    actionItems: Optional[str] = None
    rating: Optional[int] = None


_FIELD_MAP = {
    "projectName": "project_name",
    "whatWentWell": "what_went_well",
    "whatCouldImprove": "what_could_improve",
    "actionItems": "action_items",
}


@router.get("")
async def list_lessons(
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Lesson))
    items = [l.to_dict() for l in result.scalars().all()]
    if category and category != "全部":
        items = [i for i in items if i.get("category") == category]
    return {"items": items, "total": len(items)}


@router.get("/{lesson_id}")
async def get_lesson(lesson_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Lesson, lesson_id)
    if not obj:
        raise HTTPException(404, "经验教训不存在")
    return obj.to_dict()


@router.post("", status_code=201)
async def create_lesson(payload: LessonCreate, db: AsyncSession = Depends(get_db)):
    obj = Lesson(
        title=payload.title,
        project_name=payload.projectName,
        category=payload.category,
        description=payload.description,
        what_went_well=payload.whatWentWell,
        what_could_improve=payload.whatCouldImprove,
        action_items=payload.actionItems,
        rating=payload.rating,
        created_by=payload.createdBy or "当前用户",
    )
    db.add(obj)
    await db.flush()
    return obj.to_dict()


@router.put("/{lesson_id}")
async def update_lesson(lesson_id: str, payload: LessonUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Lesson, lesson_id)
    if not obj:
        raise HTTPException(404, "经验教训不存在")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, _FIELD_MAP.get(k, k), v)
    await db.flush()
    return obj.to_dict()


@router.delete("/{lesson_id}")
async def delete_lesson(lesson_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Lesson, lesson_id)
    if not obj:
        raise HTTPException(404, "经验教训不存在")
    await db.delete(obj)
    return {"ok": True}


# ============== AI 自动生成模式：结合知识库 RAG 直接生成解决办法 ==============

class LessonGenerateRequest(BaseModel):
    topic: str                              # 问题 / 场景描述
    category: Optional[str] = None          # 期望归类（可选）
    kb_scope: str = "mine"                  # "mine"=仅我的知识库 | "all"=全部可见库（需管理员）
    context_hint: Optional[str] = None      # 额外背景说明（可选）


@router.post("/generate")
async def generate_lesson(
    payload: LessonGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI 自动生成模式：先按检索范围从知识库做 RAG 召回，再把召回内容作为上下文喂给系统大模型，
    生成结构化经验教训 + 基于知识库的可落地解决办法。无 LLM 配置 / 解析失败时降级返回 RAG 检索结果。"""
    topic = (payload.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="请描述需要总结的经验或待解决的问题")

    # 1) 确定可检索的知识库范围（自己创建的 / 系统分享的 / 分享给我的；超管取全部）
    kb_ids: list[str] = []
    try:
        kb_ids = await get_accessible_kb_ids(db, current_user, scope=payload.kb_scope or "mine")
    except Exception:
        kb_ids = []

    # 2) RAG 召回知识库上下文
    context = ""
    try:
        if kb_ids:
            engine = await get_rag_engine(db)
            context = await engine.get_context(topic, kb_ids, top_k=5, max_tokens=2000)
    except Exception:
        context = ""

    _CATEGORIES = ["项目管理", "技术", "沟通", "质量", "风险", "资源", "采购", "相关方"]
    category_hint = f"\n建议归类：{payload.category}" if payload.category else ""
    hint_block = f"\n补充背景：{payload.context_hint}" if payload.context_hint else ""

    prompt = f"""你是一名资深项目管理顾问与组织过程资产（OPA）专家。请基于下方【知识库参考内容】，针对用户描述的项目经验或问题，生成一份结构化经验教训，并给出可直接落地的解决办法。

【知识库参考内容】（可能为空，若为空则凭通用项目管理方法论作答）
<<<<CONTEXT>>>>
{context or '（无相关知识库内容）'}
<<<<END>>>>

用户描述：{topic}{category_hint}{hint_block}

请严格只输出一个 JSON 对象（不要额外解释、不要代码围栏）：
{{
  "title": "不超过25字的经验标题",
  "category": "从 {",".join(_CATEGORIES)} 中选择最贴切的一项",
  "whatWentWell": "结合参考内容，总结做得好的方面（1-3条）",
  "whatCouldImprove": "需要改进的方面（1-3条）",
  "solution": "基于知识库参考给出的解决办法，分步骤、可落地、可直接复用",
  "actionItems": "后续行动项，编号列表，每条以 '- ' 开头",
  "references": ["引用的知识库文档标题，没有则为空数组"]
}}"""

    raw = None
    try:
        raw = await _llm(prompt, temperature=0.4, max_tokens=2400, timeout=120, retries=2)
    except Exception:
        raw = None

    # 3) 无 LLM 配置：降级为「仅知识库检索」，由用户手动整理
    if not raw:
        return {
            "success": True,
            "mode": "rag_only",
            "message": "未配置系统大模型，已返回知识库检索到的相关参考，请据此整理解决办法",
            "data": {
                "title": topic[:40],
                "category": payload.category or "项目管理",
                "whatWentWell": "",
                "whatCouldImprove": topic,
                "solution": context or "（知识库中暂无相关内容）",
                "actionItems": "",
                "references": [],
                "rag_context": context,
                "kb_used": kb_ids,
            },
        }

    # 4) 解析大模型输出
    parsed = _safe_json(raw)
    if not isinstance(parsed, dict):
        # 非 JSON：整段作为解决办法返回
        return {
            "success": True,
            "mode": "free_text",
            "data": {
                "title": topic[:40],
                "category": payload.category or "项目管理",
                "whatWentWell": "",
                "whatCouldImprove": topic,
                "solution": raw,
                "actionItems": "",
                "references": [],
                "rag_context": context,
                "kb_used": kb_ids,
            },
        }

    parsed.setdefault("title", topic[:40])
    parsed.setdefault("category", payload.category or "项目管理")
    parsed.setdefault("whatWentWell", "")
    parsed.setdefault("whatCouldImprove", topic)
    parsed.setdefault("solution", "")
    parsed.setdefault("actionItems", "")
    parsed.setdefault("references", [])
    return {
        "success": True,
        "mode": "ai_generated",
        "data": {
            **parsed,
            "rag_context": context,
            "kb_used": kb_ids,
        },
    }


# ============== 数据闭环：复盘自动沉淀为组织过程资产 ==============

@router.post("/{lesson_id}/archive")
async def archive_lesson(
    lesson_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await archive_lesson_to_knowledge(db, lesson_id, current_user.id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"success": True, "data": result}


@router.post("/archive-all")
async def archive_all(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await archive_all_lessons(db, current_user.id)
    return {"success": True, "data": result}

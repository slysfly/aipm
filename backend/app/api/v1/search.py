"""
PMI中国AI项目管理社区 - 搜索API

[PMBOK KA: 跨领域 (Cross-area) — 全文搜索、信息检索]
对应PMI第6版标准：信息检索

[CPMAI Phase: CPMAI Phase: Data Understanding | Domain: Data for AI — 数据探索与检索]"""

from fastapi import APIRouter, Query, HTTPException, Depends
from app.core.security import get_current_active_user
from typing import List, Optional

from app.core.search_engine import search_engine, DOC_TYPES
from app.schemas import SuccessResponse

router = APIRouter(dependencies=[Depends(get_current_active_user)])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    types: Optional[str] = Query(None, description="文档类型，逗号分隔（project,task,wiki_page,comment,user）"),
    limit: int = Query(20, ge=1, le=500, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    doc_types = None
    if types:
        doc_types = [t.strip() for t in types.split(",") if t.strip() in DOC_TYPES]

    result = await search_engine.search(
        query=q,
        doc_types=doc_types or None,
        limit=limit,
        offset=offset,
    )

    return SuccessResponse(
        data=result,
        message="搜索完成",
    )


@router.get("/search/suggest")
async def search_suggest(
    q: str = Query(..., min_length=2, description="搜索关键词"),
    limit: int = Query(10, ge=1, le=20, description="返回数量"),
):
    suggestions = await search_engine.suggest(query=q, limit=limit)

    return SuccessResponse(
        data={"suggestions": suggestions, "query": q},
        message="获取搜索建议成功",
    )

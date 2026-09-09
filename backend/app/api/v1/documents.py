"""
Documents API

[PMBOK KA: 沟通管理 (Communications) — 项目文档管理、版本控制]
对应PMI第6版标准：文档管理、版本控制
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.security import get_current_active_user
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.okr_whiteboard_document import Document

router = APIRouter(prefix="/documents", tags=["文档管理"], dependencies=[Depends(get_current_active_user)])


class DocumentCreate(BaseModel):
    title: str
    content: str = ""
    folder: str = "通用"
    author: str = ""


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    folder: Optional[str] = None


@router.get("")
async def list_documents(
    folder: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document))
    items = [d.to_dict() for d in result.scalars().all()]
    if folder:
        items = [d for d in items if d.get("folder") == folder]
    if search:
        q = search.lower()
        items = [
            d
            for d in items
            if q in d.get("title", "").lower() or q in d.get("content", "").lower()
        ]
    return {"items": items, "total": len(items)}


@router.get("/{doc_id}")
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    return doc.to_dict()


@router.post("", status_code=201)
async def create_document(payload: DocumentCreate, db: AsyncSession = Depends(get_db)):
    doc = Document(
        title=payload.title,
        content=payload.content,
        folder=payload.folder,
        author=payload.author or "当前用户",
    )
    db.add(doc)
    await db.flush()
    return doc.to_dict()


@router.put("/{doc_id}")
async def update_document(doc_id: str, payload: DocumentUpdate, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(doc, k, v)
    await db.flush()
    return doc.to_dict()


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "文档不存在")
    await db.delete(doc)
    return {"ok": True}

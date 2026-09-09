"""
Whiteboard API

[PMBOK KA: 沟通管理 | PG: 执行 (Communications/Executing) — 白板协作、可视化沟通]
对应PMI第6版标准：可视化协作
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_active_user
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.okr_whiteboard_document import Whiteboard

router = APIRouter(prefix="/whiteboards", tags=["白板管理"], dependencies=[Depends(get_current_active_user)])


class NoteSchema(BaseModel):
    id: str
    text: str
    x: float
    y: float
    color: str = "#FEF3C7"
    width: float = 180
    height: float = 140


class BoardCreate(BaseModel):
    title: str = "未命名白板"
    notes: List[NoteSchema] = []


class BoardSave(BaseModel):
    title: Optional[str] = None
    notes: Optional[List[NoteSchema]] = None


@router.get("")
async def list_boards(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Whiteboard))
    items = [b.to_dict() for b in result.scalars().all()]
    return {"items": items, "total": len(items)}


@router.get("/{board_id}")
async def get_board(board_id: str, db: AsyncSession = Depends(get_db)):
    board = await db.get(Whiteboard, board_id)
    if not board:
        raise HTTPException(404, "白板不存在")
    return board.to_dict()


@router.post("", status_code=201)
async def create_board(payload: BoardCreate, db: AsyncSession = Depends(get_db)):
    board = Whiteboard(
        title=payload.title,
        notes=[n.model_dump() for n in payload.notes],
    )
    db.add(board)
    await db.flush()
    return board.to_dict()


@router.put("/{board_id}")
async def save_board(board_id: str, payload: BoardSave, db: AsyncSession = Depends(get_db)):
    board = await db.get(Whiteboard, board_id)
    if not board:
        raise HTTPException(404, "白板不存在")
    data = payload.model_dump(exclude_unset=True)
    if "notes" in data and data["notes"] is not None:
        data["notes"] = [n.model_dump() for n in data["notes"]]
    for k, v in data.items():
        setattr(board, k, v)
    await db.flush()
    return board.to_dict()


@router.delete("/{board_id}")
async def delete_board(board_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(Whiteboard, board_id):
        raise HTTPException(404, "白板不存在")
    board = await db.get(Whiteboard, board_id)
    await db.delete(board)
    return {"ok": True}

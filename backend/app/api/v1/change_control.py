"""
变更控制 API (Change Control / CCB)

[PMBOK KA: 整合管理 | PG: 监控 (Integration/Monitoring) — 变更控制、配置管理、审批]
对应PMI第6版标准：变更控制、配置管理、变更审批流程

PMBOK 7th Principle: Change | Domain: Project Work — 驱动变革、变更管理
PMBOK 8th: Digital Change Enablement"""

from datetime import date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from app.core.security import get_current_active_user
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.pm_extras import ChangeRequest
from app.models import Project, Task, Milestone
from app.services.change_executor import execute_approved_change, get_field_whitelist

router = APIRouter(prefix="/change-requests", tags=["变更控制"], dependencies=[Depends(get_current_active_user)])


class ChangeCreate(BaseModel):
    title: str
    description: str = ""
    reason: str = ""
    impact: str = ""
    priority: str = "medium"
    category: str = "范围变更"
    status: str = "submitted"
    requestedBy: str = ""
    project_id: str  # 必须关联项目（与风险登记册一致）
    project_name: str = ""
    # 结构化变更明细：每项至少含 entity_type/entity_id/field/before/after
    change_items: List[Dict[str, Any]] = Field(default_factory=list)


class ChangeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    reason: Optional[str] = None
    impact: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    approvedBy: Optional[str] = None
    resolvedAt: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    change_items: Optional[List[Dict[str, Any]]] = None


_FIELD_MAP = {
    "requestedBy": "requested_by",
    "approvedBy": "approved_by",
    "resolvedAt": "resolved_at",
    "project_name": "project_name",
    "change_items": "change_items",
}


def _validate_items(items: List[Dict[str, Any]]) -> Optional[str]:
    """服务端二次校验：未明确"由什么变为什么"的请求一律拒绝。"""
    if not items:
        return "请至少添加一条'由什么变为什么'的变更明细"
    for i, it in enumerate(items, 1):
        if not it.get("entity_type") or not it.get("entity_id") or not it.get("field"):
            return f"第 {i} 条变更缺少必填字段（实体/字段）"
        b = (it.get("before") or "").strip() if isinstance(it.get("before"), str) else it.get("before")
        a = (it.get("after") or "").strip() if isinstance(it.get("after"), str) else it.get("after")
        # before 缺失说明未拉取当前值
        if b is None or (isinstance(b, str) and b == ""):
            return f"第 {i} 条变更缺少'原内容'（请先拉取当前值）"
        # after 必须有值
        if a is None or (isinstance(a, str) and a == ""):
            return f"第 {i} 条变更缺少'新内容'"
        # 前后必须不同
        if str(b) == str(a):
            return f"第 {i} 条变更'原内容'与'新内容'相同，未明确变化内容，不予提交"
    return None


@router.get("/")
async def list_changes(
    status: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(ChangeRequest)
    if project_id:
        q = q.where(ChangeRequest.project_id == project_id)
    result = await db.execute(q)
    items = [c.to_dict() for c in result.scalars().all()]
    if status and status != "all":
        items = [i for i in items if i.get("status") == status]
    return {"items": items, "total": len(items)}


@router.get("/whitelist")
async def field_whitelist():
    """暴露可变更字段清单（含 label/kind/enum options），供前端表单生成器使用。"""
    return get_field_whitelist()


@router.get("/entities/{project_id}")
async def list_entities(project_id: str, db: AsyncSession = Depends(get_db)):
    """供变更表单选择实体：返回该项目下的任务与里程碑精简信息（含白名单字段当前值）。"""
    q_t = select(Task).where(Task.project_id == project_id).order_by(Task.wbs_code.asc().nulls_last(), Task.name.asc())
    tasks = (await db.execute(q_t)).scalars().all()
    q_m = select(Milestone).where(Milestone.project_id == project_id).order_by(Milestone.due_date.asc().nulls_last())
    milestones = (await db.execute(q_m)).scalars().all()
    return {
        "tasks": [
            {
                "id": t.id, "name": t.name or "", "wbs_code": t.wbs_code or "",
                "description": t.description or "",
                "status": t.status or "", "priority": int(t.priority) if t.priority is not None else None,
                "progress": float(t.progress or 0),
                "estimated_hours": float(t.estimated_hours or 0),
                "planned_start": t.planned_start.isoformat() if t.planned_start else "",
                "planned_end": t.planned_end.isoformat() if t.planned_end else "",
            }
            for t in tasks
        ],
        "milestones": [
            {
                "id": m.id, "name": m.name or "", "description": m.description or "",
                "due_date": m.due_date.isoformat() if m.due_date else "",
                "status": m.status or "",
            }
            for m in milestones
        ],
    }


@router.get("/{change_id}")
async def get_change(change_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChangeRequest, change_id)
    if not obj:
        raise HTTPException(404, "变更请求不存在")
    return obj.to_dict()


@router.post("/", status_code=201)
async def create_change(payload: ChangeCreate, db: AsyncSession = Depends(get_db)):
    err = _validate_items(payload.change_items)
    if err:
        raise HTTPException(422, err)
    obj = ChangeRequest(
        title=payload.title,
        description=payload.description,
        reason=payload.reason,
        impact=payload.impact,
        priority=payload.priority,
        category=payload.category,
        status=payload.status,
        requested_by=payload.requestedBy or "当前用户",
        project_id=payload.project_id,
        project_name=payload.project_name or "",
        change_items=list(payload.change_items or []),
        execution_log=[],
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj.to_dict()


@router.put("/{change_id}")
async def update_change(change_id: str, payload: ChangeUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChangeRequest, change_id)
    if not obj:
        raise HTTPException(404, "变更请求不存在")
    data = payload.model_dump(exclude_unset=True)

    # 若要写入新的变更明细，先校验
    if "change_items" in data:
        err = _validate_items(data["change_items"] or [])
        if err:
            raise HTTPException(422, err)

    # 必须先记录审批前状态，再应用 setattr（否则 obj.status 已被改写为 approved）
    prev_status = obj.status

    # 进入终态时自动补充解决日期
    if data.get("status") in ("approved", "rejected", "implemented") and "resolvedAt" not in data:
            obj.resolved_at = date.today().strftime("%Y-%m-%d")

    for k, v in data.items():
        setattr(obj, _FIELD_MAP.get(k, k), v)

    # ── 核心：审批通过 → AI 自动落地每一个变更项 + 校验 ────────────────────────────
    # will_be_approved：本次请求把状态置为 approved，且此前未处于 approved/implemented
    will_be_approved = data.get("status") == "approved" and prev_status not in ("approved", "implemented")
    if will_be_approved:
        log = await execute_approved_change(db, obj)
        obj.execution_log = log
        # 全部 verified 才推进到 implemented；否则保留 approved 但写明失败明细
        if log and all(item.get("verified") for item in log):
            obj.status = "implemented"
        else:
            obj.status = "approved"
        if not obj.resolved_at:
            obj.resolved_at = date.today().strftime("%Y-%m-%d")

    await db.commit()
    await db.refresh(obj)
    return obj.to_dict()


@router.delete("/{change_id}")
async def delete_change(change_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ChangeRequest, change_id)
    if not obj:
        raise HTTPException(404, "变更请求不存在")
    await db.delete(obj)
    await db.commit()
    return {"ok": True}

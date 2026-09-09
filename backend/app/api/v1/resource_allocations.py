"""
资源排程 API (Resource Allocation / Schedule)
============================================

数据模型沿用 `ResourceAllocation`：
- 用户提供基础信息：资源 / 项目 / 任务名 / 起止日期 / 每日工时 / 优先级
- AI 优化：根据"日产能（resource.capacity，默认 8h）"检测过载，
  生成"把低优先级条目挪到空闲日"建议；用户可逐条应用，也可一键全部应用；
  每次应用都会把原值快照到 original_* 字段，便于撤销。

路由：
- GET    /resource-allocations                列表（带过滤）
- POST   /resource-allocations                录入排程
- GET    /resource-allocations/{id}           详情
- PUT    /resource-allocations/{id}           更新
- DELETE /resource-allocations/{id}           删除
- POST   /resource-allocations/optimize       分析过载 + 生成建议（无副作用）
- POST   /resource-allocations/optimize/apply 应用建议（支持多条）
- POST   /resource-allocations/{id}/undo      撤销单条 AI 调整
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _coerce_json_dict(raw) -> dict:
    """PostgreSQL JSON 列历史数据可能存为 str，统一 json.loads 兜底。"""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}
    return {}

from app.core.security import get_current_user
from app.db.session import get_db
from app.models import User, Resource, ResourceAllocation, Task

router = APIRouter(
    prefix="/resource-allocations",
    tags=["资源排程"],
    dependencies=[Depends(get_current_user)],
)


# ── Schemas ────────────────────────────────────────────────────────────

class AllocationCreate(BaseModel):
    project_id: str
    resource_id: str
    task_id: Optional[str] = None
    task_title: str = ""
    start_date: date
    end_date: date
    hours_per_day: float = Field(..., gt=0, le=24, description="每日工时，> 0 且 ≤ 24")
    daily_hours: Optional[Dict[str, float]] = None  # {"YYYY-MM-DD": hours} 覆盖
    priority: int = Field(3, ge=1, le=5)
    status: str = "planned"
    notes: str = ""


class AllocationUpdate(BaseModel):
    task_id: Optional[str] = None
    task_title: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    hours_per_day: Optional[float] = None
    daily_hours: Optional[Dict[str, float]] = None
    priority: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ApplyRequest(BaseModel):
    """支持两种传参：
    1) 完整建议：suggestions=[{allocationId, toStart, toEnd, toDailyHours, reason}, ...]（来自 /optimize 原样转发）
    2) 仅 ID 列表：suggestion_ids=["abc", "def"]，或 "all"（需在调用前已有建议上下文，否则只标记 is_ai_move 并将日期前移 1 天）
    """
    suggestions: List[Dict[str, Any]] = Field(default_factory=list)
    suggestion_ids: Optional[Any] = None  # List[str] | "all"
    project_id: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────

def _to_dict(a: ResourceAllocation) -> Dict[str, Any]:
    return {
        "id": a.id,
        "projectId": a.project_id,
        "resourceId": a.resource_id,
        "taskId": a.task_id or "",
        "taskTitle": a.task_title or (a.task.name if a.task else ""),
        "startDate": a.start_date.isoformat() if a.start_date else "",
        "endDate": a.end_date.isoformat() if a.end_date else "",
        "hoursPerDay": float(a.hours_per_day or 0),
        "dailyHours": _coerce_json_dict(a.daily_hours),
        "priority": int(a.priority or 3),
        "status": a.status or "planned",
        "notes": a.notes or "",
        "isAiMove": bool(a.is_ai_move),
        "optimizationReason": a.optimization_reason or "",
        "createdAt": a.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if a.created_at else "",
        "updatedAt": a.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ") if a.updated_at else "",
    }


def _validate(payload: AllocationCreate) -> None:
    if not payload.task_id and not (payload.task_title or "").strip():
        raise HTTPException(422, "请填写任务名称，或关联到具体任务")
    if payload.end_date < payload.start_date:
        raise HTTPException(422, "结束日期不能早于开始日期")
    if (payload.end_date - payload.start_date).days > 366:
        raise HTTPException(422, "排程跨度不能超过 366 天")
    if payload.daily_hours:
        for k, v in payload.daily_hours.items():
            try:
                date.fromisoformat(k)
            except ValueError:
                raise HTTPException(422, f"daily_hours 键 {k!r} 不是 YYYY-MM-DD")
            if v <= 0 or v > 24:
                raise HTTPException(422, f"daily_hours[{k}] = {v} 须在 (0, 24]")


def _expand_to_cells(a: ResourceAllocation, win_start: date, win_end: date) -> List[tuple[str, float]]:
    """把一条排程展开成 (date_str, hours) 列表，与窗口取交集。"""
    s = a.start_date
    e = a.end_date
    # 兼容旧式单日：allocated_date
    if not s and a.allocated_date:
        s = e = a.allocated_date
    if not s or not e or e < s:
        return []
    s = max(s, win_start)
    e = min(e, win_end)
    if e < s:
        return []
    cells: List[tuple[str, float]] = []
    dh: Dict[str, float] = {}
    src_dh = _coerce_json_dict(a.daily_hours)
    if src_dh:
        for k, v in src_dh.items():
            try:
                dh[date.fromisoformat(k).isoformat()] = float(v)
            except (ValueError, TypeError):
                pass
    cur = s
    while cur <= e:
        ds = cur.isoformat()
        h = float(dh.get(ds) or a.hours_per_day or a.allocated_hours or 0)
        if h > 0:
            cells.append((ds, h))
        cur += timedelta(days=1)
    return cells


# ── CRUD ───────────────────────────────────────────────────────────────

@router.get("")
async def list_allocations(
    project_id: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(ResourceAllocation)
    if project_id:
        q = q.where(ResourceAllocation.project_id == project_id)
    if resource_id:
        q = q.where(ResourceAllocation.resource_id == resource_id)
    if start_date:
        q = q.where(ResourceAllocation.end_date >= start_date)
    if end_date:
        q = q.where(ResourceAllocation.start_date <= end_date)
    rows = (await db.execute(q.order_by(ResourceAllocation.start_date))).scalars().all()
    return {"items": [_to_dict(r) for r in rows], "total": len(rows)}


@router.post("", status_code=201)
async def create_allocation(
    payload: AllocationCreate,
    db: AsyncSession = Depends(get_db),
):
    _validate(payload)
    # 校验资源存在
    res = await db.get(Resource, payload.resource_id)
    if not res:
        raise HTTPException(422, f"资源 {payload.resource_id} 不存在")
    obj = ResourceAllocation(
        project_id=payload.project_id,
        resource_id=payload.resource_id,
        task_id=payload.task_id,
        task_title=(payload.task_title or "").strip(),
        start_date=payload.start_date,
        end_date=payload.end_date,
        hours_per_day=payload.hours_per_day,
        daily_hours=payload.daily_hours or {},
        priority=payload.priority,
        status=payload.status,
        notes=payload.notes or "",
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _to_dict(obj)


@router.get("/{alloc_id}")
async def get_allocation(alloc_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ResourceAllocation, alloc_id)
    if not obj:
        raise HTTPException(404, "排程不存在")
    return _to_dict(obj)


@router.put("/{alloc_id}")
async def update_allocation(
    alloc_id: str,
    payload: AllocationUpdate,
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(ResourceAllocation, alloc_id)
    if not obj:
        raise HTTPException(404, "排程不存在")
    data = payload.model_dump(exclude_unset=True)
    # 终态校验
    if "start_date" in data or "end_date" in data:
        ns = data.get("start_date", obj.start_date)
        ne = data.get("end_date", obj.end_date)
        if ne < ns:
            raise HTTPException(422, "结束日期不能早于开始日期")
    for k, v in data.items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return _to_dict(obj)


@router.delete("/{alloc_id}")
async def delete_allocation(alloc_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(ResourceAllocation, alloc_id)
    if not obj:
        raise HTTPException(404, "排程不存在")
    await db.delete(obj)
    await db.commit()
    return {"ok": True}


# ── AI 优化：分析过载 + 生成建议（无副作用） ────────────────────────────

@router.post("/optimize")
async def optimize_allocations(
    project_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(...),
    end_date: Optional[date] = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """分析窗口内过载，生成挪动建议。建议默认挪到原日期之后最近的空闲日。"""
    if end_date < start_date:
        raise HTTPException(422, "结束日期不能早于开始日期")
    if (end_date - start_date).days > 92:
        raise HTTPException(422, "分析窗口不能超过 92 天")

    # 1) 拉窗口内排程
    q = (
        select(ResourceAllocation)
        .where(ResourceAllocation.end_date >= start_date)
        .where(ResourceAllocation.start_date <= end_date)
    )
    if project_id:
        q = q.where(ResourceAllocation.project_id == project_id)
    allocs = (await db.execute(q)).scalars().all()

    # 2) 拉资源（含 capacity）
    res_ids = {a.resource_id for a in allocs}
    resources: Dict[str, Resource] = {}
    if res_ids:
        rows = (await db.execute(select(Resource).where(Resource.id.in_(res_ids)))).scalars().all()
        resources = {r.id: r for r in rows}

    # 3) 展开到 (resource, date) 单元格
    load: Dict[tuple[str, str], List[tuple[ResourceAllocation, float]]] = {}
    for a in allocs:
        for ds, h in _expand_to_cells(a, start_date, end_date):
            load.setdefault((a.resource_id, ds), []).append((a, h))

    # 4) 找过载单元格
    overloaded: List[Dict[str, Any]] = []
    for (res_id, ds), items in load.items():
        res = resources.get(res_id)
        cap = float(res.capacity or 8) if res else 8.0
        total = sum(h for _, h in items)
        if total > cap:
            overloaded.append({
                "resourceId": res_id,
                "resourceName": res.name if res else "?",
                "date": ds,
                "totalHours": round(total, 2),
                "capacity": cap,
                "overload": round(total - cap, 2),
                "items": [
                    {
                        "allocationId": a.id,
                        "title": a.task_title or (a.task.name if a.task else "(无标题)"),
                        "hours": h,
                        "priority": int(a.priority or 3),
                    }
                    for a, h in items
                ],
            })
    overloaded.sort(key=lambda x: (x["date"], -x["overload"]))

    # 5) 找每个资源的空闲日（占用 < 50% 容量）
    slack: Dict[str, List[str]] = {rid: [] for rid in res_ids}
    n_days = (end_date - start_date).days + 1
    for rid in res_ids:
        cap = float(resources[rid].capacity or 8) if resources.get(rid) else 8.0
        for i in range(n_days):
            d = start_date + timedelta(days=i)
            ds = d.isoformat()
            used = sum(h for (r, dd), items in load.items() if r == rid and dd == ds for _, h in items)
            if used < cap * 0.5:
                slack[rid].append(ds)
        slack[rid].sort()

    # 6) 生成建议：每个过载挑最低优先级挪到最近空闲日（避免重复挪动同一条）
    suggestions: List[Dict[str, Any]] = []
    moved_ids: set = set()
    for ov in overloaded:
        rid = ov["resourceId"]
        if not slack.get(rid):
            continue
        cand = [it for it in sorted(ov["items"], key=lambda x: -x["priority"]) if it["allocationId"] not in moved_ids]
        if not cand:
            continue
        victim = cand[0]
        target = next((d for d in slack[rid] if d > ov["date"]), slack[rid][0] if slack[rid] else None)
        if not target:
            continue
        a = next((x for x in allocs if x.id == victim["allocationId"]), None)
        if not a or not a.start_date:
            continue
        delta = (date.fromisoformat(target) - a.start_date).days
        if delta == 0:
            continue
        new_start = a.start_date + timedelta(days=delta)
        new_end = (a.end_date + timedelta(days=delta)) if a.end_date else new_start
        new_dh: Optional[Dict[str, float]] = None
        src_dh = _coerce_json_dict(a.daily_hours)
        if src_dh:
            new_dh = {}
            for k, v in src_dh.items():
                try:
                    kd = date.fromisoformat(k)
                    new_dh[(kd + timedelta(days=delta)).isoformat()] = float(v)
                except (ValueError, TypeError):
                    pass
        suggestions.append({
            "allocationId": a.id,
            "fromStart": a.start_date.isoformat(),
            "fromEnd": a.end_date.isoformat() if a.end_date else None,
            "toStart": new_start.isoformat(),
            "toEnd": new_end.isoformat(),
            "toDailyHours": new_dh,
            "targetDate": target,
            "overloadDate": ov["date"],
            "freesHours": victim["hours"],
            "reason": (
                f"{ov['resourceName']} 在 {ov['date']} 过载 {ov['overload']:.1f}h，"
                f"建议把【{victim['title']}】从 {a.start_date.isoformat()} 挪到 {target}（空闲日）"
            ),
        })
        moved_ids.add(a.id)
        slack[rid] = [d for d in slack[rid] if d != target]

    return {
        "window": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        "overloadedCells": overloaded,
        "suggestions": suggestions,
        "summary": {
            "overloadedCount": len(overloaded),
            "suggestionCount": len(suggestions),
            "totalOverloadHours": round(sum(o["overload"] for o in overloaded), 2),
        },
    }


# ── 应用建议（支持多条，可作"全部应用"入口） ────────────────────────────

@router.post("/optimize/apply")
async def apply_optimization(
    payload: ApplyRequest,
    db: AsyncSession = Depends(get_db),
):
    """应用 AI 优化建议。
    - payload.suggestions: 完整建议列表（来自 /optimize 原样）
    - payload.suggestion_ids: 仅 ID 列表（["id1","id2"] 或 "all"），此时后端会针对这些排程做一次"标记+微调"（日期 +1 天）
    """
    applied: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    # ── 模式 A：完整建议 ──
    if payload.suggestions:
        for s in payload.suggestions:
            aid = s.get("allocationId")
            a = await db.get(ResourceAllocation, aid) if aid else None
            if not a:
                errors.append({"allocationId": aid, "error": "排程不存在"})
                continue
            try:
                if not a.is_ai_move:
                    a.original_start_date = a.start_date
                    a.original_end_date = a.end_date
                    a.original_daily_hours = a.daily_hours
                    a.original_hours_per_day = a.hours_per_day
                if s.get("toStart"):
                    a.start_date = date.fromisoformat(s["toStart"])
                if s.get("toEnd"):
                    a.end_date = date.fromisoformat(s["toEnd"])
                if s.get("toDailyHours") is not None:
                    a.daily_hours = s["toDailyHours"]
                a.is_ai_move = True
                a.optimization_reason = s.get("reason", "")
                applied.append({"allocationId": a.id, "ok": True})
            except Exception as e:  # noqa: BLE001
                errors.append({"allocationId": aid, "error": f"应用失败: {e}"})

    # ── 模式 B：仅 ID 列表（用于"全部应用"快捷入口） ──
    elif payload.suggestion_ids:
        ids: List[str] = []
        if payload.suggestion_ids == "all":
            # 全部当前 project 的非 AI 排程
            q = select(ResourceAllocation)
            if payload.project_id:
                q = q.where(ResourceAllocation.project_id == payload.project_id)
            rows = (await db.execute(q)).scalars().all()
            ids = [r.id for r in rows]
        elif isinstance(payload.suggestion_ids, list):
            ids = [str(x) for x in payload.suggestion_ids if x]
        for aid in ids:
            a = await db.get(ResourceAllocation, aid)
            if not a:
                errors.append({"allocationId": aid, "error": "排程不存在"})
                continue
            try:
                if not a.is_ai_move:
                    a.original_start_date = a.start_date
                    a.original_end_date = a.end_date
                    a.original_daily_hours = a.daily_hours
                    a.original_hours_per_day = a.hours_per_day
                # 简易挪动：把开始日期推迟到 +1 天
                if a.start_date:
                    a.start_date = a.start_date + timedelta(days=1)
                if a.end_date:
                    a.end_date = a.end_date + timedelta(days=1)
                a.is_ai_move = True
                a.optimization_reason = "AI 自动微调（推迟 1 天）"
                applied.append({"allocationId": a.id, "ok": True, "toStart": a.start_date.isoformat() if a.start_date else None})
            except Exception as e:  # noqa: BLE001
                errors.append({"allocationId": aid, "error": f"应用失败: {e}"})

    if applied:
        await db.commit()
    return {"applied": applied, "errors": errors, "appliedCount": len(applied)}


# ── 撤销 AI 调整 ───────────────────────────────────────────────────────

@router.post("/{alloc_id}/undo")
async def undo_ai_move(alloc_id: str, db: AsyncSession = Depends(get_db)):
    a = await db.get(ResourceAllocation, alloc_id)
    if not a:
        raise HTTPException(404, "排程不存在")
    if not a.is_ai_move:
        raise HTTPException(400, "该排程不是 AI 调整的，无需撤销")
    a.start_date = a.original_start_date
    a.end_date = a.original_end_date
    a.daily_hours = a.original_daily_hours
    a.hours_per_day = a.original_hours_per_day
    a.is_ai_move = False
    a.optimization_reason = ""
    a.original_start_date = None
    a.original_end_date = None
    a.original_daily_hours = None
    a.original_hours_per_day = None
    await db.commit()
    return {"ok": True, "id": a.id}

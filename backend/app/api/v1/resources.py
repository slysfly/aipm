"""
资源管理 API（复用 Resource 模型）

[PMBOK KA: 资源管理 (Resource Management) — 资源分配、资源日历、团队组建、RACI矩阵]
对应PMI第6版标准：资源分配、团队组建、资源日历
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime, time, timedelta
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.db.session import get_db
from app.core.security import get_current_user
from app.core.responses import success, fail
from app.models import User, Resource, Task, Project, ResourceAllocation

router = APIRouter(prefix="/resources", tags=["资源管理"])


def _coerce_json_dict(raw) -> dict:
    """PostgreSQL JSON 列历史数据可能存为 str，统一 json.loads 兜底。空/None/非法一律返 {}。"""
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


class ResourceCreate(BaseModel):
    name: str
    resource_type: str = "person"
    skills: List[str] = []
    capacity: float = 8.0
    cost_rate: float = 0
    department: Optional[str] = None
    user_id: Optional[str] = None


class ResourceUpdate(BaseModel):
    name: Optional[str] = None
    resource_type: Optional[str] = None
    skills: Optional[List[str]] = None
    capacity: Optional[float] = None
    cost_rate: Optional[float] = None
    department: Optional[str] = None
    user_id: Optional[str] = None
    is_active: Optional[bool] = None


def _res_to_dict(r: Resource) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "resource_type": r.resource_type,
        "skills": r.skills or [],
        "capacity": float(r.capacity) if r.capacity is not None else 0.0,
        "cost_rate": float(r.cost_rate) if r.cost_rate is not None else 0.0,
        "department": r.department,
        "user_id": r.user_id,
        "is_active": r.is_active,
    }


@router.get("")
async def list_resources(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    res = await db.execute(select(Resource).order_by(desc(Resource.created_at)))
    return [_res_to_dict(r) for r in res.scalars().all()]


@router.post("", status_code=201)
async def create_resource(payload: ResourceCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    obj = Resource(**payload.model_dump())
    db.add(obj)
    await db.flush()
    return success(data=_res_to_dict(obj))


@router.put("/{res_id}")
async def update_resource(res_id: str, payload: ResourceUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    obj = await db.get(Resource, res_id)
    if not obj:
        fail("资源不存在", status_code=404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(obj, k, v)
    await db.flush()
    return _res_to_dict(obj)


@router.delete("/{res_id}")
async def delete_resource(res_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    obj = await db.get(Resource, res_id)
    if not obj:
        raise HTTPException(404, "资源不存在")
    await db.delete(obj)
    return success(message="删除成功")


@router.get("/calendar")
async def resource_calendar(
    start_date: Optional[date] = Query(None, description="时间窗口开始日期 (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="时间窗口结束日期 (YYYY-MM-DD)"),
    project_id: Optional[str] = Query(None, description="按项目过滤"),
    resource_type: Optional[str] = Query("person", description="资源类型过滤，all=全部"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    资源日历：以负责人（资源）为泳道，展示其在时间窗口内负责的各项任务。
    谁（资源）在什么时候（计划起止）干什么事儿（任务 / 项目）。
    """
    today = date.today()
    if not start_date:
        start_date = today - timedelta(days=7)
    if not end_date:
        end_date = today + timedelta(days=28)

    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)

    query = (
        select(Task)
        .join(Project, Task.project_id == Project.id)
        .where(
            Project.is_deleted == False,
            Task.is_deleted == False,
            Task.is_milestone == False,
            Task.assignee_id.isnot(None),
            Task.planned_start.isnot(None),
            Task.planned_start <= end_dt,
            func.coalesce(Task.planned_end, Task.planned_start) >= start_dt,
        )
    )
    if project_id:
        query = query.where(Task.project_id == project_id)
    tasks = (await db.execute(query)).scalars().all()

    # 项目元数据
    proj_ids = {t.project_id for t in tasks}
    projs = {}
    if proj_ids:
        projs = {p.id: p for p in (await db.execute(select(Project).where(Project.id.in_(proj_ids)))).scalars().all()}
    proj_name = {pid: (p.name or "未命名项目") for pid, p in projs.items()}
    proj_color = {pid: (p.color or "#1890ff") for pid, p in projs.items()}

    # 资源（负责人）元数据
    assignee_ids = [t.assignee_id for t in tasks if t.assignee_id]
    users = {}
    resources = {}
    if assignee_ids:
        users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(assignee_ids)))).scalars().all()}
        resources = {r.user_id: r for r in (await db.execute(select(Resource).where(Resource.user_id.in_(assignee_ids)))).scalars().all()}

    def _match_type(rtype: str) -> bool:
        return resource_type == "all" or rtype == resource_type

    swimlanes = []
    for aid in assignee_ids:
        u = users.get(aid)
        r = resources.get(aid)
        rtype = r.resource_type if r else "person"
        if not _match_type(rtype):
            continue
        name = (r.name if r and r.name else None) or (u.full_name if u and u.full_name else None) or (u.username if u else "未知成员")
        swimlanes.append({
            "id": aid,
            "name": name,
            "type": rtype,
            "department": r.department if r and r.department else (u.department if u else None),
            "skills": (r.skills or []) if r else [],
            "userId": aid,
            "resourceId": r.id if r else None,
        })

    events = []
    for t in tasks:
        if not t.assignee_id:
            continue
        r = resources.get(t.assignee_id)
        if not _match_type(r.resource_type if r else "person"):
            continue
        start = t.planned_start
        end = t.planned_end or t.planned_start
        if not start:
            continue
        events.append({
            "id": t.id,
            "resourceId": t.assignee_id,
            "taskId": t.id,
            "title": t.name,
            "projectId": t.project_id,
            "projectName": proj_name.get(t.project_id, "未命名项目"),
            "projectColor": proj_color.get(t.project_id, "#1890ff"),
            "start": start.isoformat(),
            "end": end.isoformat() if end else start.isoformat(),
            "progress": float(t.progress or 0),
            "status": t.status,
            "priority": int(t.priority) if t.priority is not None else 3,
        })

    # 把 Resource 反向索引（resource_id → Resource），用于把 allocation.resource_id 映射到 swimlane(user_id)
    resource_by_id = {r.id: r for r in resources.values()}

    # ── 拉取窗口内的 ResourceAllocation（用户录入的排程） ──────────────────
    q_a = (
        select(ResourceAllocation)
        .where(ResourceAllocation.end_date >= start_dt)
        .where(ResourceAllocation.start_date <= end_dt)
    )
    if project_id:
        q_a = q_a.where(ResourceAllocation.project_id == project_id)
    allocations = (await db.execute(q_a)).scalars().all()

    # 把窗口内 allocation 涉及的 resource 也并入 resource_by_id（避免无任务时找不到）
    alloc_res_ids = {a.resource_id for a in allocations if a.resource_id} - set(resource_by_id.keys())
    if alloc_res_ids:
        extra = (await db.execute(select(Resource).where(Resource.id.in_(alloc_res_ids)))).scalars().all()
        for r in extra:
            resource_by_id[r.id] = r

    # 关键：把窗口内有排程的 resource 也加入 swimlane，即便该资源没在该窗口承担任务
    alloc_synth_swimlanes: Dict[str, Dict[str, object]] = {}
    for a in allocations:
        r_obj = resource_by_id.get(a.resource_id)
        if not r_obj or not _match_type(r_obj.resource_type or "person"):
            continue
        sk = r_obj.user_id or r_obj.id
        if not sk or sk in alloc_synth_swimlanes:
            continue
        if sk in {sw["id"] for sw in swimlanes}:  # 已有真 swimlane
            continue
        alloc_synth_swimlanes[sk] = {
            "id": sk,
            "name": r_obj.name or "未命名资源",
            "type": r_obj.resource_type or "person",
            "department": r_obj.department,
            "skills": r_obj.skills or [],
            "userId": r_obj.user_id or "",
            "resourceId": r_obj.id,
            "capacity": float(r_obj.capacity) if r_obj.capacity is not None else None,
            "synthetic": True,  # 标记为「仅有排程、无任务」的资源
        }
    if alloc_synth_swimlanes:
        swimlanes.extend(alloc_synth_swimlanes.values())

    # 每日工时累计：(swimlane_key=user_id, date_str) -> hours
    daily_totals: Dict[tuple[str, str], float] = {}
    for a in allocations:
        r_obj = resource_by_id.get(a.resource_id)
        if not r_obj:
            continue  # resource 已删
        if not _match_type(r_obj.resource_type or "person"):
            continue
        swimlane_key = r_obj.user_id or r_obj.id  # 日历 swimlane 优先按 user_id 排；未关联用户则用 resource.id
        if not swimlane_key:
            continue
        s = a.start_date
        e = a.end_date
        if not s and a.allocated_date:
            s = e = a.allocated_date
        if not s or not e or e < s:
            continue
        # 与窗口求交
        cur = max(s, start_date)
        end_cur = min(e, end_date)
        if end_cur < cur:
            continue
        proj = projs.get(a.project_id)
        proj_nm = proj.name if proj else (proj_name.get(a.project_id, "未命名项目"))
        proj_cl = (proj.color if proj and proj.color else None) or proj_color.get(a.project_id, "#7C3AED")
        dh = _coerce_json_dict(a.daily_hours)
        # 展开为每日 cells；hours_per_day 可被 daily_hours 覆盖
        while cur <= end_cur:
            ds = cur.isoformat()
            h = float(dh.get(ds) or a.hours_per_day or a.allocated_hours or 0)
            if h > 0:
                daily_totals[(swimlane_key, ds)] = daily_totals.get((swimlane_key, ds), 0) + h
                events.append({
                    "id": a.id,
                    "resourceId": swimlane_key,
                    "taskId": a.task_id or "",
                    "allocationId": a.id,
                    "title": a.task_title or (a.task.name if a.task else ""),
                    "projectId": a.project_id,
                    "projectName": proj_nm,
                    "projectColor": proj_cl,
                    "start": s.isoformat(),
                    "end": e.isoformat(),
                    "hoursPerDay": h,
                    "progress": 0,
                    "status": a.status or "planned",
                    "priority": int(a.priority or 3),
                    "isAllocation": True,
                    "isAiMove": bool(a.is_ai_move),
                })
            cur += timedelta(days=1)

    # 构造 dailyTotals 数组 + 资源 capacity
    daily_totals_arr: List[Dict[str, object]] = []
    cap_by_user: Dict[str, float] = {}
    for uid, r in resources.items():
        if r.capacity is not None:
            cap_by_user[uid] = float(r.capacity)
    for (rid_key, ds), hours in daily_totals.items():
        cap = cap_by_user.get(rid_key, 8.0)
        daily_totals_arr.append({
            "resourceId": rid_key,
            "date": ds,
            "totalHours": round(hours, 2),
            "capacity": cap,
            "overload": round(max(0, hours - cap), 2),
        })
    daily_totals_arr.sort(key=lambda x: (x["resourceId"], x["date"]))

    # 把 capacity 也带回 resources（前端不用再单独查）
    for sw in swimlanes:
        sw["capacity"] = cap_by_user.get(sw["id"], 8.0)

    return {
        "range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "resources": swimlanes,
        "events": events,
        "dailyTotals": daily_totals_arr,
    }

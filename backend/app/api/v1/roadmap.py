"""
产品路线图 API (Product Roadmap) — 三视图版

[PMBOK KA: 范围管理/进度管理 | PG: 规划 — 产品路线图、价值流、技术路线、发布管理]
三视图：价值流图(Value Stream) / 技术路线图(Tech Roadmap) / 发布管理(Release)
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case, text

from app.db.session import get_db
from app.models.pm_extras import RoadmapItem
from app.models import Release, ReleaseTask, Task, Project
from app.core.security import get_current_active_user

router = APIRouter(prefix="/roadmap", tags=["产品路线图"], dependencies=[Depends(get_current_active_user)])


# ── Schemas ──────────────────────────────────────────────

class RoadmapCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "planned"
    priority: str = "medium"
    quarter: str = ""
    date: str = ""
    start_date: str = ""
    end_date: str = ""
    view_type: str = "release"          # value_stream | tech_roadmap | release
    category: str = ""
    project_id: Optional[str] = None
    release_id: Optional[str] = None
    tech_stack: str = ""
    maturity_level: str = ""
    owner: str = ""
    progress: int = 0


class RoadmapUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    quarter: Optional[str] = None
    date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    view_type: Optional[str] = None
    category: Optional[str] = None
    project_id: Optional[str] = None
    release_id: Optional[str] = None
    tech_stack: Optional[str] = None
    maturity_level: Optional[str] = None
    owner: Optional[str] = None
    progress: Optional[int] = None


# ── CRUD ─────────────────────────────────────────────────

@router.get("")
async def list_roadmap(
    view_type: Optional[str] = Query(None, description="按视图筛选: value_stream/tech_roadmap/release"),
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(RoadmapItem)
    count_q = select(func.count(RoadmapItem.id))

    if view_type:
        query = query.where(RoadmapItem.view_type == view_type)
        count_q = count_q.where(RoadmapItem.view_type == view_type)
    if project_id:
        query = query.where(RoadmapItem.project_id == project_id)
        count_q = count_q.where(RoadmapItem.project_id == project_id)
    if status:
        query = query.where(RoadmapItem.status == status)
        count_q = count_q.where(RoadmapItem.status == status)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.order_by(
        RoadmapItem.quarter.asc(), RoadmapItem.start_date.asc().nulls_last(), RoadmapItem.created_at.desc()
    ))
    items = [r.to_dict() for r in result.scalars().all()]
    return {"items": items, "total": total}


# ── 三视图专用端点（必须在 /{item_id} 之前！） ───────────

@router.get("/dashboard/summary")
async def roadmap_dashboard(project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """路线图总览仪表盘 — 各视图统计摘要"""
    base = select(RoadmapItem)
    if project_id:
        base = base.where(RoadmapItem.project_id == project_id)

    all_items = (await db.execute(base)).scalars().all()

    by_view = {"value_stream": [], "tech_roadmap": [], "release": []}
    by_status = {"planned": 0, "in_progress": 0, "done": 0, "cancelled": 0}
    by_priority = {"high": 0, "medium": 0, "low": 0}

    for it in all_items:
        d = it.to_dict()
        vt = d.get("viewType", "release")
        if vt in by_view:
            by_view[vt].append(d)
        s = d.get("status", "planned")
        if s in by_status:
            by_status[s] += 1
        p = d.get("priority", "medium")
        if p in by_priority:
            by_priority[p] += 1

    # 关联项目列表
    proj_ids = list(set(it.project_id for it in all_items if it.project_id))
    projects = []
    if proj_ids:
        proj_result = await db.execute(select(Project).where(Project.id.in_(proj_ids)))
        projects = [{"id": p.id, "name": p.name} for p in proj_result.scalars().all()]

    return {
        "total": len(all_items),
        "byView": {k: len(v) for k, v in by_view.items()},
        "byStatus": by_status,
        "byPriority": by_priority,
        "projects": projects,
        "recentItems": sorted([it.to_dict() for it in all_items],
                              key=lambda x: x.get("createdAt", ""), reverse=True)[:5],
    }


@router.get("/value-stream/map")
async def value_stream_map(project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    价值流图数据 — 按阶段分组展示从「需求」到「交付」的价值流动
    返回：stages（各阶段节点）、flow（流转关系）、metrics（效率指标）
    """
    query = select(RoadmapItem).where(RoadmapItem.view_type == "value_stream")
    if project_id:
        query = query.where(RoadmapItem.project_id == project_id)
    query = query.order_by(RoadmapItem.category.asc(), RoadmapItem.priority.desc(), RoadmapItem.created_at.asc())

    items = (await db.execute(query)).scalars().all()

    # 预定义价值流阶段（可被 category 覆盖）
    default_stages = [
        {"key": "idea", "label": "需求构思", "order": 1},
        {"key": "design", "label": "设计规划", "order": 2},
        {"key": "develop", "label": "开发实现", "order": 3},
        {"key": "test", "label": "测试验证", "order": 4},
        {"key": "deploy", "label": "部署交付", "order": 5},
        {"key": "operate", "label": "运营反馈", "order": 6},
    ]

    # 按 category 分组到阶段
    stage_map = {}   # stage_key -> items
    for it in items:
        d = it.to_dict()
        cat = (d.get("category") or "").lower()
        # 模糊匹配到预定义阶段
        matched_key = None
        for ds in default_stages:
            if ds["key"] in cat or ds["label"][:2] in cat or cat in ds["label"]:
                matched_key = ds["key"]
                break
        if not matched_key:
            matched_key = "other"
        stage_map.setdefault(matched_key, []).append(d)

    stages = []
    for ds in default_stages:
        si = stage_map.get(ds["key"], [])
        done_count = sum(1 for i in si if i.get("status") == "done")
        stages.append({
            **ds,
            "itemCount": len(si),
            "doneCount": done_count,
            "progress": round(done_count / len(si) * 100) if si else 0,
            "items": si,
        })

    # 未分类的归入 other
    if stage_map.get("other"):
        stages.append({
            "key": "other", "label": "其他", "order": 99,
            "itemCount": len(stage_map["other"]),
            "doneCount": sum(1 for i in stage_map["other"] if i.get("status") == "done"),
            "items": stage_map["other"],
        })

    # 计算总体指标
    total = len(items)
    done_total = sum(1 for it in items if it.status == "done")
    ip_total = sum(1 for it in items if it.status == "in_progress")

    return {
        "stages": stages,
        "metrics": {
            "totalItems": total,
            "completed": done_total,
            "inProgress": ip_total,
            "overallProgress": round(done_total / total * 100) if total else 0,
            "stageCount": len([s for s in stages if s["itemCount"] > 0]),
        },
    }


@router.get("/tech-roadmap/timeline")
async def tech_roadmap_timeline(project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    技术路线图时间线 — 按技术域/季度展示技术演进计划
    返回：lanes（技术泳道）、timeline（时间轴事件）、stacks（技术栈清单）
    """
    query = select(RoadmapItem).where(RoadmapItem.view_type == "tech_roadmap")
    if project_id:
        query = query.where(RoadmapItem.project_id == project_id)
    query = query.order_by(RoadmapItem.start_date.asc().nulls_last(), RoadmapItem.quarter.asc(), RoadmapItem.created_at.asc())

    items = (await db.execute(query)).scalars().all()

    # 按技术域（category）分组为泳道
    lanes = {}
    stacks = set()
    quarters = set()
    maturity_counts = {"research": 0, "prototype": 0, "production": 0, "deprecated": 0}

    for it in items:
        d = it.to_dict()
        lane = d.get("category") or "未分类"
        lanes.setdefault(lane, []).append(d)

        # 收集技术栈标签
        for ts in (d.get("techStack") or "").split(","):
            ts = ts.strip()
            if ts:
                stacks.add(ts)

        q = d.get("quarter", "")
        if q:
            quarters.add(q)

        ml = d.get("maturityLevel", "")
        if ml in maturity_counts:
            maturity_counts[ml] += 1

    lane_list = []
    for name, items_in_lane in sorted(lanes.items()):
        done = sum(1 for i in items_in_lane if i.get("status") == "done")
        lane_list.append({
            "name": name,
            "items": items_in_lane,
            "itemCount": len(items_in_lane),
            "doneCount": done,
            "progress": round(done / len(items_in_lane) * 100) if items_in_lane else 0,
        })

    return {
        "lanes": lane_list,
        "stacks": sorted(stacks),
        "quarters": sorted(quarters),
        "maturitySummary": maturity_counts,
        "totalItems": len(items),
    }


@router.get("/release/board")
async def release_board(project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    发布管理看板 — 整合 RoadmapItem(release类型) + Release 表数据
    返回：releases（版本列表）、roadmapItems（关联里程碑）、ganttData（甘特数据）
    """
    # 1. 路线图中 release 类型的条目
    rm_query = select(RoadmapItem).where(RoadmapItem.view_type == "release")
    if project_id:
        rm_query = rm_query.where(RoadmapItem.project_id == project_id)
    rm_query = rm_query.order_by(RoadmapItem.quarter.asc(), RoadmapItem.date.asc())
    rm_items = (await db.execute(rm_query)).scalars().all()

    # 2. Release 表中的正式版本
    rel_query = select(Release)
    if project_id:
        rel_query = rel_query.where(Release.project_id == project_id)
    rel_query = rel_query.order_by(Release.release_date.asc().nulls_last(), Release.created_at.desc())
    releases = (await db.execute(rel_query)).scalars().all()

    # 3. 为每个 Release 统计任务完成情况
    release_data = []
    for rel in releases:
        rd = {
            "id": rel.id,
            "name": rel.name,
            "version": rel.version,
            "status": rel.status,
            "projectId": rel.project_id or "",
            "releaseDate": rel.release_date.strftime("%Y-%m-%d") if rel.release_date else "",
            "description": rel.description or "",
            "taskCount": 0,
            "completedTaskCount": 0,
        }
        # 关联任务统计
        rt_result = await db.execute(
            select(ReleaseTask).where(ReleaseTask.release_id == rel.id)
        )
        rts = rt_result.scalars().all()
        rd["taskCount"] = len(rts)
        if rts:
            task_ids = [rt.task_id for rt in rts]
            done_r = await db.execute(
                select(func.count(Task.id)).where(Task.id.in_(task_ids), Task.status == "done")
            )
            rd["completedTaskCount"] = done_r.scalar() or 0
        release_data.append(rd)

    # 4. 甘特数据（合并 roadmap milestones + releases）
    gantt = []
    for it in rm_items:
        d = it.to_dict()
        gantt.append({
            "id": d["id"],
            "name": d["title"],
            "type": "milestone",
            "start": d.get("startDate") or d.get("date") or "",
            "end": d.get("endDate") or d.get("date") or "",
            "status": d.get("status"),
            "progress": d.get("progress", 0),
            "quarter": d.get("quarter", ""),
            "projectId": d.get("projectId", ""),
        })
    for rd in release_data:
        gantt.append({
            "id": rd["id"],
            "name": f"{rd['name']} v{rd['version']}",
            "type": "release",
            "start": rd.get("releaseDate", ""),
            "end": rd.get("releaseDate", ""),
            "status": rd.get("status"),
            "progress": round(rd["completedTaskCount"] / rd["taskCount"] * 100) if rd["taskCount"] else 0,
            "projectId": rd.get("projectId", ""),
        })

    # 按日期排序
    gantt.sort(key=lambda x: x.get("start") or "")

    return {
        "milestones": [it.to_dict() for it in rm_items],
        "releases": release_data,
        "ganttData": gantt,
        "summary": {
            "totalMilestones": len(rm_items),
            "totalReleases": len(release_data),
            "releasedCount": sum(1 for r in release_data if r["status"] == "released"),
            "planningCount": sum(1 for r in release_data if r["status"] in ("planning", "in_progress")),
        },
    }


# ── 单项 CRUD（动态路由必须放最后）──────────────────────

@router.get("/{item_id}")
async def get_item(item_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(RoadmapItem, item_id)
    if not obj:
        raise HTTPException(404, "里程碑不存在")
    return obj.to_dict()


@router.post("", status_code=201)
async def create_item(payload: RoadmapCreate, db: AsyncSession = Depends(get_db)):
    if payload.project_id:
        proj = await db.get(Project, payload.project_id)
        if not proj:
            raise HTTPException(400, f"项目 {payload.project_id} 不存在")

    obj = RoadmapItem(
        title=payload.title,
        description=payload.description,
        status=payload.status,
        priority=payload.priority,
        quarter=payload.quarter,
        date=payload.date,
        start_date=payload.start_date,
        end_date=payload.end_date,
        view_type=payload.view_type,
        category=payload.category,
        project_id=payload.project_id,
        release_id=payload.release_id,
        tech_stack=payload.tech_stack,
        maturity_level=payload.maturity_level,
        owner=payload.owner,
        progress=payload.progress,
    )
    db.add(obj)
    await db.flush()
    return obj.to_dict()


@router.put("/{item_id}")
async def update_item(item_id: str, payload: RoadmapUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(RoadmapItem, item_id)
    if not obj:
        raise HTTPException(404, "里程碑不存在")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await db.flush()
    return obj.to_dict()


@router.delete("/{item_id}")
async def delete_item(item_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(RoadmapItem, item_id)
    if not obj:
        raise HTTPException(404, "里程碑不存在")
    await db.delete(obj)
    return {"ok": True}

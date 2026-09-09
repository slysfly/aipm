"""
统一 LLM 异步任务 handler 注册中心。

把 4 类大模型能力（WBS 生成 / 项目分析 / 风险预测 / 表单智能填充 / 经验教训总结）
统一接入异步任务框架：
- 端点只负责「创建 AsyncTask + dispatch_task」，立即返回 task_id；
- handler 在后台执行：调 ai_service → 持久化业务数据 → 推送实时进度 → 广播 data_changed；
- 前端经 /ws/events 订阅 task_progress / task_done / data_changed 实时刷新。

这样任意大模型任务都在后台完成，前端无需阻塞等待，且多用户可实时看到数据变更。
"""
import logging
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Task, Risk, Lesson, ChangeRequest, Milestone, User
from app.models.async_task import AsyncTask, AsyncTaskStatus
from app.services.async_task_runner import register_handler, publish_progress
from app.core.websocket import publish_to_all, publish_event
from app.services.ai_service import ai_service
from app.services.kb_access import resolve_ai_kb

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. generate_wbs —— WBS 生成并回写任务/风险
# ---------------------------------------------------------------------------
async def _run_generate_wbs(db: AsyncSession, task: AsyncTask, params: Dict[str, Any]):
    from app.api.v1.tasks import generate_wbs_code

    project_name = params.get("project_name") or "未命名项目"
    project_description = params.get("project_description") or ""
    industry_type = params.get("industry_type") or "it_software"
    constraints = params.get("constraints") or {}
    project_id = params.get("project_id")
    save_to_tasks = bool(params.get("save_to_tasks"))

    # 解析并校验 AI 生成使用的知识库（单 scope：公开 / 本人私密，二者二选一）
    user = await db.get(User, task.user_id)
    kb_id = await resolve_ai_kb(db, params.get("kb_id"), user)

    await publish_progress(task, 10, "正在调用大模型生成 WBS...", db)
    result = await ai_service.generate_wbs(
        project_name=project_name,
        project_description=project_description,
        industry_type=industry_type,
        constraints=constraints,
        kb_id=kb_id,
    )

    created_task_ids = []
    created_risk_names = []
    if project_id and save_to_tasks:
        project = (await db.execute(
            select(Project).where(Project.id == project_id, Project.is_deleted == False)
        )).scalar_one_or_none()
        if not project:
            return {"success": False, "error": "项目不存在"}
        code_to_task_id = {}
        try:
            for item in result.get("wbs_structure", []):
                name = item.get("name") or item.get("title") or "未命名任务"
                wc = (item.get("wbs_code") or "").strip()
                parent_code = ".".join(wc.split(".")[:-1]) if "." in wc else None
                parent_task_id = code_to_task_id.get(parent_code) if parent_code else None
                if parent_task_id:
                    sib = (await db.execute(
                        select(func.count(Task.id)).where(
                            Task.project_id == project_id,
                            Task.parent_task_id == parent_task_id,
                            Task.is_deleted == False,
                        )
                    )).scalar() + 1
                else:
                    sib = (await db.execute(
                        select(func.count(Task.id)).where(
                            Task.project_id == project_id,
                            Task.parent_task_id == None,
                            Task.is_deleted == False,
                        )
                    )).scalar() + 1
                wbs_code = wc if wc else generate_wbs_code(parent_code, sib)
                t = Task(
                    project_id=project_id,
                    parent_task_id=parent_task_id,
                    wbs_code=wbs_code,
                    name=name,
                    description=item.get("description", ""),
                    level=(wc.count(".") + 1) if wc else 1,
                    status="todo",
                    estimated_hours=item.get("duration_days") or item.get("estimated_hours") or 0,
                )
                db.add(t)
                await db.flush()
                if wc:
                    code_to_task_id[wc] = t.id
                created_task_ids.append(t.id)
            await db.commit()
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass
            raise

        for risk_item in result.get("risk_identification", []):
            rname = risk_item.get("name") or risk_item.get("title") or "风险"
            try:
                probability = float(risk_item.get("probability", 0.5) or 0.5)
                impact = float(risk_item.get("impact", 0.5) or 0.5)
            except Exception:
                probability, impact = 0.5, 0.5
            risk = Risk(
                project_id=project_id,
                name=rname,
                description=risk_item.get("description", ""),
                category=risk_item.get("category", "technical"),
                probability=probability,
                impact=impact,
                risk_score=probability * impact,
                status="identified",
            )
            db.add(risk)
            created_risk_names.append(rname)
        await db.commit()

        result["created_task_ids"] = created_task_ids
        result["created_task_count"] = len(created_task_ids)

        await publish_progress(task, 85, f"已回写 {len(created_task_ids)} 个任务", db)
        # 广播：任务与风险数据已变更（多用户协作实时刷新）
        await publish_to_all({
            "type": "data_changed",
            "entity": "tasks",
            "project_id": project_id,
            "action": "created",
        })
        await publish_to_all({
            "type": "data_changed",
            "entity": "risks",
            "project_id": project_id,
            "action": "created",
        })

    await publish_progress(task, 100, "WBS 生成完成", db)
    return result


# ---------------------------------------------------------------------------
# 2. analyze_project —— 项目健康度 AI 分析
# ---------------------------------------------------------------------------
async def _run_analyze_project(db: AsyncSession, task: AsyncTask, params: Dict[str, Any]):
    project_id = params.get("project_id")
    project = (await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )).scalar_one_or_none()
    if not project:
        return {"success": False, "error": "项目不存在"}

    task_stats = (await db.execute(
        select(
            func.count(Task.id).label("total"),
            func.sum(case((Task.status == 'done', 1), else_=0)).label("completed"),
            func.sum(case((Task.status == 'in_progress', 1), else_=0)).label("in_progress"),
            func.avg(Task.progress).label("avg_progress"),
        ).where(Task.project_id == project_id, Task.is_deleted == False)
    )).one()

    risk_stats = (await db.execute(
        select(
            func.count(Risk.id).label("total"),
            func.sum(case((Risk.status != 'closed', 1), else_=0)).label("active"),
            func.avg(Risk.risk_score).label("avg_score"),
        ).where(Risk.project_id == project_id)
    )).one()

    project_data = {
        "id": project.id,
        "name": project.name,
        "total_tasks": task_stats.total or 0,
        "completed_tasks": task_stats.completed or 0,
        "in_progress_tasks": task_stats.in_progress or 0,
        "avg_progress": task_stats.avg_progress or 0,
        "total_risks": risk_stats.total or 0,
        "active_risks": risk_stats.active or 0,
        "avg_risk_score": risk_stats.avg_score or 0,
        "baseline_start": project.baseline_start.isoformat() if project.baseline_start else None,
        "baseline_end": project.baseline_end.isoformat() if project.baseline_end else None,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
    }

    kb_id = await resolve_ai_kb(db, params.get("kb_id"), await db.get(User, task.user_id))

    await publish_progress(task, 30, "正在聚合项目数据", db)
    await publish_progress(task, 60, "正在调用大模型分析", db)
    result = await ai_service.analyze_project(project_data, kb_id=kb_id)
    await publish_progress(task, 100, "分析完成", db)
    await publish_to_all({
        "type": "data_changed",
        "entity": "analysis",
        "project_id": project_id,
        "action": "created",
    })
    return result


# ---------------------------------------------------------------------------
# 3. predict_risk —— 项目风险预测
# ---------------------------------------------------------------------------
async def _run_predict_risk(db: AsyncSession, task: AsyncTask, params: Dict[str, Any]):
    project_id = params.get("project_id")
    project = (await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )).scalar_one_or_none()
    if not project:
        return {"success": False, "error": "项目不存在"}

    task_stats = (await db.execute(
        select(
            func.count(Task.id).label("total"),
            func.sum(case((Task.status == 'done', 1), else_=0)).label("completed"),
            func.avg(Task.progress).label("avg_progress"),
        ).where(Task.project_id == project_id, Task.is_deleted == False)
    )).one()

    risk_stats = (await db.execute(
        select(
            func.count(Risk.id).label("total"),
            func.sum(case((Risk.status != 'closed', 1), else_=0)).label("active"),
            func.avg(Risk.risk_score).label("avg_score"),
        ).where(Risk.project_id == project_id)
    )).one()

    project_data = {
        "id": project.id,
        "name": project.name,
        "total_tasks": task_stats.total or 0,
        "completed_tasks": task_stats.completed or 0,
        "avg_progress": task_stats.avg_progress or 0,
        "active_risks": risk_stats.active or 0,
        "avg_risk_score": risk_stats.avg_score or 0,
    }

    kb_id = await resolve_ai_kb(db, params.get("kb_id"), await db.get(User, task.user_id))

    await publish_progress(task, 30, "正在聚合项目数据", db)
    await publish_progress(task, 60, "正在调用大模型预测风险", db)
    result = await ai_service.predict_risks(project_data, kb_id=kb_id)
    await publish_progress(task, 100, "风险预测完成", db)
    await publish_to_all({
        "type": "data_changed",
        "entity": "risks",
        "project_id": project_id,
        "action": "predicted",
    })
    return result


# ---------------------------------------------------------------------------
# 4. assist_fill —— 智能表单填充
# ---------------------------------------------------------------------------
async def _run_assist_fill(db: AsyncSession, task: AsyncTask, params: Dict[str, Any]):
    form_type = params.get("form_type") or "task"
    fields = params.get("fields") or {}
    context = params.get("context") or {}
    await publish_progress(task, 30, "正在分析已填字段", db)
    await publish_progress(task, 70, "正在调用大模型补全", db)
    result = await ai_service.assist_fill(form_type=form_type, fields=fields, context=context)
    await publish_progress(task, 100, "补全完成", db)
    return result


# ---------------------------------------------------------------------------
# 5. summarize_lessons —— AI 总结经验教训（从 projects.py 迁入统一托管）
# ---------------------------------------------------------------------------
_LESSON_CATEGORIES = ["项目管理", "技术", "沟通", "质量", "风险", "资源", "采购", "相关方"]


async def _run_summarize_lessons(db: AsyncSession, task: AsyncTask, params: Dict[str, Any]):
    import json as _json
    project_id = params.get("project_id")
    user_id = task.user_id

    project = await db.get(Project, project_id)
    if not project:
        return {"success": False, "error": "项目不存在"}

    await publish_progress(task, 10, "正在聚合项目数据", db)

    tasks = (await db.execute(select(Task).where(Task.project_id == project_id))).scalars().all()
    risks = (await db.execute(select(Risk).where(Risk.project_id == project_id))).scalars().all()
    changes = (await db.execute(select(ChangeRequest).where(ChangeRequest.project_id == project_id))).scalars().all()
    milestones = (await db.execute(select(Milestone).where(Milestone.project_id == project_id))).scalars().all()

    done = sum(1 for t in tasks if (t.status or "todo") == "done")
    overdue = sum(1 for t in tasks if getattr(t, "due_date", None) and t.due_date < datetime.now() and (t.status or "todo") != "done")
    progress = round(done / len(tasks) * 100) if tasks else 0

    def _brief(items, fields):
        out = []
        for it in items[:25]:
            d = {f: getattr(it, f, None) for f in fields}
            out.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in d.items()})
        return out

    context = {
        "project": {
            "name": project.name,
            "status": project.status,
            "methodology": project.project_type or "",  # project_type 存储的是敏捷/瀑布/混合等方法论
            "start_date": project.start_date.isoformat() if hasattr(project.start_date, "isoformat") else project.start_date,
            "end_date": project.end_date.isoformat() if hasattr(project.end_date, "isoformat") else project.end_date,
            "budget": float(project.budget or 0),
        },
        "progress": {"total": len(tasks), "done": done, "overdue": overdue, "percent": progress},
        "tasks": _brief(tasks, ["name", "status", "priority", "progress", "due_date", "assignee_id"]),
        "risks": _brief(risks, ["name", "status", "risk_score", "response_strategy"]),
        "changes": _brief(changes, ["title", "status"]),
        "milestones": _brief(milestones, ["name", "status", "due_date"]),
    }
    context_text = _json.dumps(context, ensure_ascii=False, default=str)

    await publish_progress(task, 40, "已聚合项目数据，正在调用大模型", db)

    from app.services.ai.out_of_box_agents import _llm, _safe_json
    prompt = f"""你是一名资深项目管理顾问与组织过程资产(OPA)专家。请基于下方【项目实际数据】(JSON)，
提炼出本项目值得沉淀的"经验教训"(Lessons Learned)。
要求：
- 聚焦可复用、对未来项目有价值的内容：哪些做法有效、哪些踩了坑、后续如何改进。
- 结合数据中的逾期任务、高风险项、频繁变更、里程碑延误等信号，给出针对性洞察。
- 生成 2-4 条经验教训，每条结构化输出。
- 只输出一个 JSON 数组，不要额外解释、不要代码围栏，例如：
[{{"title":"不超过25字","category":"从{','.join(_LESSON_CATEGORIES)}中选择","whatWentWell":"做得好的方面1-2条","whatCouldImprove":"待改进方面1-2条","actionItems":"- 步骤1\\n- 步骤2","rating":4}}]

【项目实际数据】
{context_text}"""

    raw = None
    try:
        raw = await _llm(prompt, temperature=0.5, max_tokens=2400, timeout=120, retries=2)
    except Exception:
        raw = None

    if not raw:
        return {"success": True, "mode": "no_llm", "message": "未配置系统大模型，无法自动生成。", "lessons": [], "archives": []}

    await publish_progress(task, 75, "AI 已生成经验教训，正在沉淀到知识库", db)

    parsed = _safe_json(raw)
    items = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])

    lessons = []
    archives = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item.setdefault("title", f"{project.name} 项目经验")
        item.setdefault("category", "项目管理")
        item.setdefault("whatWentWell", "")
        item.setdefault("whatCouldImprove", "")
        item.setdefault("actionItems", "")
        item.setdefault("rating", 3)
        lesson = Lesson(
            title=str(item["title"])[:500],
            project_name=project.name,
            category=str(item["category"]),
            description=f"由 AI 基于项目《{project.name}》实际数据自动总结",
            what_went_well=str(item["whatWentWell"]),
            what_could_improve=str(item["whatCouldImprove"]),
            action_items=str(item["actionItems"]),
            rating=int(item["rating"]) if isinstance(item["rating"], (int, float)) else 3,
            created_by=user_id,
        )
        db.add(lesson)
        await db.flush()
        try:
            from app.services.knowledge_auto_service import auto_ingest
            arc = await auto_ingest(
                db, "lesson", lesson.title,
                f"经验教训：{lesson.title}\n做得好：{lesson.what_went_well}\n待改进：{lesson.what_could_improve}\n行动项：{lesson.action_items}",
                project_id=project_id, created_by=user_id,
            )
            archives.append(arc)
        except Exception as e:
            archives.append({"lesson_id": lesson.id, "error": str(e)})
        lessons.append({"id": lesson.id, "title": lesson.title, "category": lesson.category})

    await publish_progress(task, 95, "正在广播数据变更", db)
    await publish_to_all({
        "type": "data_changed",
        "entity": "lessons",
        "project_id": project_id,
        "action": "created",
        "project_name": project.name,
    })

    return {
        "success": True,
        "mode": "ai_generated",
        "project_id": project_id,
        "project_name": project.name,
        "lessons": lessons,
        "archives": archives,
    }


def register_llm_handlers():
    """注册全部 LLM 异步任务 handler。在应用启动时调用一次。"""
    register_handler("generate_wbs", _run_generate_wbs)
    register_handler("analyze_project", _run_analyze_project)
    register_handler("predict_risk", _run_predict_risk)
    register_handler("assist_fill", _run_assist_fill)
    register_handler("summarize_lessons", _run_summarize_lessons)
    logger.info("LLM 异步任务 handler 注册完成：generate_wbs / analyze_project / predict_risk / assist_fill / summarize_lessons")


# 模块导入即注册，确保 app 启动后 handlers 立即可用
register_llm_handlers()

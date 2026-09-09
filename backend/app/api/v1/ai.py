"""
[PMBOK KA: 范围管理/进度管理 (Scope/Schedule) — AI生成WBS、项目分析、风险预测]
对应PMI第6版标准：AI生成WBS、项目分析、风险管理

[CPMAI Phase: CPMAI Phase: Business Understanding/Model Development | Domain: AI Fundamentals — AI驱动的业务分析与模型交互]
PMBOK 7th Principle: Tailoring/Complexity | Domain: Planning — AI辅助裁剪、应对复杂性
PMBOK 8th: AI-Native Project Intelligence"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import Project, Task, User, Risk
from app.schemas import (
    WBSGenerationRequest,
    WBSGenerationResponse,
    AIChatRequest,
    AIChatResponse,
)
from app.core.security import get_current_user
from app.services.ai_service import ai_service
from app.api.v1.tasks import generate_wbs_code
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/generate-wbs", response_model=WBSGenerationResponse)
async def generate_wbs(
    request: WBSGenerationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        result = await ai_service.generate_wbs(
            project_name=request.project_name,
            project_description=request.project_description,
            industry_type=request.industry_type,
            constraints=request.constraints or {},
            kb_id=request.kb_id,
        )

        # 将生成的 WBS 结构回写为真实任务（打通 AI 产出 -> 业务数据）
        created_task_ids = []
        if request.project_id and request.save_to_tasks:
            project = (await db.execute(
                select(Project).where(Project.id == request.project_id, Project.is_deleted == False)
            )).scalar_one_or_none()
            if not project:
                raise HTTPException(status_code=404, detail="项目不存在")

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
                                Task.project_id == request.project_id,
                                Task.parent_task_id == parent_task_id,
                                Task.is_deleted == False,
                            )
                        )).scalar() + 1
                    else:
                        sib = (await db.execute(
                            select(func.count(Task.id)).where(
                                Task.project_id == request.project_id,
                                Task.parent_task_id == None,
                                Task.is_deleted == False,
                            )
                        )).scalar() + 1

                    wbs_code = wc if wc else generate_wbs_code(parent_code, sib)
                    task = Task(
                        project_id=request.project_id,
                        parent_task_id=parent_task_id,
                        wbs_code=wbs_code,
                        name=name,
                        description=item.get("description", ""),
                        level=(wc.count(".") + 1) if wc else 1,
                        status="todo",
                        estimated_hours=item.get("duration_days") or item.get("estimated_hours") or 0,
                    )
                    # 同一事务内累计父任务 + 所有子实例；flush 仅用于获取 UUID 主键以便父子关联
                    db.add(task)
                    await db.flush()
                    if wc:
                        code_to_task_id[wc] = task.id
                    created_task_ids.append(task.id)
                # 父任务 + N 子实例一次性原子提交（事务隔离）：任一子任务失败则整体回滚
                await db.commit()
            except Exception:
                # 显式 rollback 兜底：避免残留半截 WBS 树
                try:
                    await db.rollback()
                except Exception:
                    pass
                raise

            # 将 AI 识别的风险回写为风险表
            created_risk_names = []
            for risk_item in result.get("risk_identification", []):
                rname = risk_item.get("name") or risk_item.get("title") or "风险"
                try:
                    probability = float(risk_item.get("probability", 0.5) or 0.5)
                    impact = float(risk_item.get("impact", 0.5) or 0.5)
                except Exception:
                    probability, impact = 0.5, 0.5
                risk = Risk(
                    project_id=request.project_id,
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

                # 自动知识沉淀（AutoRAG）：将 AI 识别的风险入库
                try:
                    from app.services.knowledge_auto_service import auto_ingest
                    await auto_ingest(
                        db,
                        "risk",
                        rname,
                        f"风险：{rname}\n描述：{risk_item.get('description', '')}\n类别：{risk.category}",
                        project_id=request.project_id,
                        created_by=current_user.id,
                    )
                except Exception as e:
                    logger.warning("风险自动知识沉淀失败（已忽略）: %s", e, exc_info=True)
            await db.commit()

            # 触发 Webhook（风险创建），打通 AI 风险产出 -> 外部系统
            try:
                from app.services.webhook_service import trigger_webhook_event
                from app.schemas.webhook import WebhookEvent
                await trigger_webhook_event(
                    db,
                    WebhookEvent.RISK_CREATED,
                    {
                        "event": "risk.created",
                        "data": {
                            "project_id": request.project_id,
                            "created_risks": created_risk_names,
                        },
                        "timestamp": datetime.now().isoformat(),
                    },
                    project_id=request.project_id,
                )
            except Exception as e:
                logger.warning("风险创建 Webhook 触发失败（已忽略）: %s", e, exc_info=True)

            result["created_task_ids"] = created_task_ids
            result["created_task_count"] = len(created_task_ids)

        return WBSGenerationResponse(**result)
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WBS generation failed: {str(e)}")


@router.post("/chat")
async def ai_chat(
    request: AIChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        result = await ai_service.chat(
            message=request.message,
            project_id=request.project_id,
            kb_id=request.kb_id,
        )
        return AIChatResponse(**result)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI chat failed: {str(e)}")


@router.post("/chat/stream")
async def ai_chat_stream(
    request: AIChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    async def event_generator():
        try:
            async for chunk in ai_service.stream_chat(
                message=request.message,
                project_id=request.project_id,
                kb_id=request.kb_id,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: AI服务暂时不可用：{str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/analyze-project/{project_id}", response_model=Dict[str, Any])
async def analyze_project(
    project_id: str,
    kb_id: Optional[str] = Query(None, description="参照的知识库 ID（公开/本人私密二选一）。为空则默认使用公开知识库"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    task_stats_result = await db.execute(
        select(
            func.count(Task.id).label("total"),
            func.sum(case((Task.status == 'done', 1), else_=0)).label("completed"),
            func.sum(case((Task.status == 'in_progress', 1), else_=0)).label("in_progress"),
            func.avg(Task.progress).label("avg_progress"),
        ).where(Task.project_id == project_id, Task.is_deleted == False)
    )
    task_stats = task_stats_result.one()

    risk_stats_result = await db.execute(
        select(
            func.count(Risk.id).label("total"),
            func.sum(case((Risk.status != 'closed', 1), else_=0)).label("active"),
            func.avg(Risk.risk_score).label("avg_score"),
        ).where(Risk.project_id == project_id)
    )
    risk_stats = risk_stats_result.one()

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

    try:
        result = await ai_service.analyze_project(project_data, kb_id=kb_id)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Project analysis failed: {str(e)}")


@router.post("/predict-risk/{project_id}", response_model=Dict[str, Any])
async def predict_risk(
    project_id: str,
    kb_id: Optional[str] = Query(None, description="参照的知识库 ID（公开/本人私密二选一）。为空则默认使用公开知识库"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.is_deleted == False)
    )
    project = project_result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    task_stats_result = await db.execute(
        select(
            func.count(Task.id).label("total"),
            func.sum(case((Task.status == 'done', 1), else_=0)).label("completed"),
            func.avg(Task.progress).label("avg_progress"),
        ).where(Task.project_id == project_id, Task.is_deleted == False)
    )
    task_stats = task_stats_result.one()

    risk_stats_result = await db.execute(
        select(
            func.count(Risk.id).label("total"),
            func.sum(case((Risk.status != 'closed', 1), else_=0)).label("active"),
            func.avg(Risk.risk_score).label("avg_score"),
        ).where(Risk.project_id == project_id)
    )
    risk_stats = risk_stats_result.one()

    project_data = {
        "id": project.id,
        "name": project.name,
        "total_tasks": task_stats.total or 0,
        "completed_tasks": task_stats.completed or 0,
        "avg_progress": task_stats.avg_progress or 0,
        "active_risks": risk_stats.active or 0,
        "avg_risk_score": risk_stats.avg_score or 0,
    }

    try:
        result = await ai_service.predict_risks(project_data, kb_id=kb_id)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Risk prediction failed: {str(e)}")

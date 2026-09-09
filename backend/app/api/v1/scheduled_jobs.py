"""
PMI中国AI项目管理社区 - 定时任务API路由

[PMBOK KA: 进度管理 | PG: 执行 (Schedule/Executing) — 定时任务、自动化作业]
对应PMI第6版标准：定时任务
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.models import User, ScheduledJob, JobExecutionLog
from app.schemas.scheduled_task import (
    ScheduledJobCreate, ScheduledJobUpdate, ScheduledJobResponse,
    ScheduledJobListResponse, JobExecutionLogResponse, JobExecutionLogListResponse,
    ScheduledJobRunNowResponse, ScheduledJobToggleResponse,
    CronPreset, CronPresetListResponse
)
from app.schemas import SuccessResponse
from app.core.exceptions import NotFoundException, ValidationException
from app.core.security import get_current_user
from app.services.scheduler_service import scheduler_service, JobConfig

router = APIRouter()


# Cron预设
CRON_PRESETS = [
    CronPreset(label="每分钟", value="* * * * *", description="每分钟执行一次"),
    CronPreset(label="每小时", value="0 * * * *", description="每小时的第0分钟执行"),
    CronPreset(label="每天", value="0 0 * * *", description="每天凌晨执行"),
    CronPreset(label="每周一", value="0 0 * * 1", description="每周一凌晨执行"),
    CronPreset(label="每月1日", value="0 0 1 * *", description="每月1日凌晨执行"),
    CronPreset(label="工作日每天", value="0 9 * * 1-5", description="工作日早上9点执行"),
    CronPreset(label="每15分钟", value="*/15 * * * *", description="每15分钟执行一次"),
    CronPreset(label="每30分钟", value="*/30 * * * *", description="每30分钟执行一次"),
]


@router.post("/", response_model=ScheduledJobResponse, status_code=201)
async def create_scheduled_job(
    job_in: ScheduledJobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 验证cron表达式格式
    cron_parts = job_in.cron_expression.split()
    if len(cron_parts) != 5:
        raise ValidationException(message="Cron表达式必须是5个字段（分 时 日 月 周）")

    job = ScheduledJob(
        name=job_in.name,
        description=job_in.description,
        job_type=job_in.job_type,
        cron_expression=job_in.cron_expression,
        parameters=job_in.parameters,
        is_active=job_in.is_active,
        created_by=current_user.id,
    )

    # 计算下次执行时间
    next_run = scheduler_service._get_next_run_time(job_in.cron_expression)
    job.next_run_at = next_run

    db.add(job)
    await db.commit()
    await db.refresh(job)

    # 如果调度器已启动且任务激活，添加到调度器
    if scheduler_service._running and job.is_active:
        await scheduler_service._schedule_job(job)

    return job


@router.get("/", response_model=ScheduledJobListResponse)
async def list_scheduled_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    job_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = select(ScheduledJob)
    count_query = select(func.count(ScheduledJob.id))

    conditions = []
    if job_type:
        conditions.append(ScheduledJob.job_type == job_type)
    if is_active is not None:
        conditions.append(ScheduledJob.is_active == is_active)

    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(ScheduledJob.created_at.desc())

    result = await db.execute(query)
    jobs = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return ScheduledJobListResponse(
        items=[ScheduledJobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/presets", response_model=CronPresetListResponse)
async def get_cron_presets(
    current_user: User = Depends(get_current_user)
):
    return CronPresetListResponse(items=CRON_PRESETS)


@router.get("/{job_id}", response_model=ScheduledJobResponse)
async def get_scheduled_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise NotFoundException(message="定时任务不存在")

    return job


@router.put("/{job_id}", response_model=ScheduledJobResponse)
async def update_scheduled_job(
    job_id: str,
    job_in: ScheduledJobUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise NotFoundException(message="定时任务不存在")

    update_data = job_in.model_dump(exclude_unset=True)

    # 验证cron表达式
    if "cron_expression" in update_data:
        cron_parts = update_data["cron_expression"].split()
        if len(cron_parts) != 5:
            raise ValidationException(message="Cron表达式必须是5个字段（分 时 日 月 周）")

    for field, value in update_data.items():
        setattr(job, field, value)

    # 如果更新了cron表达式，重新计算下次执行时间
    if "cron_expression" in update_data:
        job.next_run_at = scheduler_service._get_next_run_time(job.cron_expression)
        if scheduler_service._running:
            if job.is_active:
                await scheduler_service._schedule_job(job)
            else:
                await scheduler_service._unschedule_job(job_id)

    job.updated_at = datetime.now()
    await db.commit()
    await db.refresh(job)

    return job


@router.delete("/{job_id}", response_model=SuccessResponse)
async def delete_scheduled_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise NotFoundException(message="定时任务不存在")

    await scheduler_service._unschedule_job(job_id)
    await db.delete(job)
    await db.commit()

    return SuccessResponse(message="定时任务删除成功")


@router.post("/{job_id}/run-now", response_model=ScheduledJobRunNowResponse)
async def run_scheduled_job_now(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise NotFoundException(message="定时任务不存在")

    log = await scheduler_service.execute_job_now(job_id)

    return ScheduledJobRunNowResponse(
        id=job_id,
        log_id=log.id,
        status=log.status,
        message="任务已立即执行"
    )


@router.post("/{job_id}/pause", response_model=ScheduledJobToggleResponse)
async def pause_scheduled_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job = await scheduler_service.pause_job(job_id)
    return ScheduledJobToggleResponse(
        id=job_id,
        is_active=job.is_active,
        message="定时任务已暂停"
    )


@router.post("/{job_id}/resume", response_model=ScheduledJobToggleResponse)
async def resume_scheduled_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    job = await scheduler_service.resume_job(job_id)
    return ScheduledJobToggleResponse(
        id=job_id,
        is_active=job.is_active,
        message="定时任务已恢复"
    )


@router.get("/{job_id}/logs", response_model=JobExecutionLogListResponse)
async def get_scheduled_job_logs(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise NotFoundException(message="定时任务不存在")

    query = select(JobExecutionLog).where(JobExecutionLog.job_id == job_id)
    count_query = select(func.count(JobExecutionLog.id)).where(JobExecutionLog.job_id == job_id)

    if status:
        query = query.where(JobExecutionLog.status == status)
        count_query = count_query.where(JobExecutionLog.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(JobExecutionLog.started_at.desc())

    result = await db.execute(query)
    logs = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return JobExecutionLogListResponse(
        items=[JobExecutionLogResponse.model_validate(l) for l in logs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

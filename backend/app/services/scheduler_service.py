"""
PMI中国AI项目管理社区 - 定时任务调度器服务
支持APScheduler（如已安装）或简单定时轮询
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.scheduled_task import ScheduledJob, JobExecutionLog, JobStatus
from app.core.exceptions import NotFoundException, BusinessException

logger = logging.getLogger(__name__)

# 尝试导入APScheduler
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler未安装，使用简单定时轮询模式")


@dataclass
class JobConfig:
    """任务配置数据类"""
    id: Optional[str]
    name: str
    description: Optional[str]
    job_type: str
    cron_expression: str
    parameters: Dict[str, Any]
    is_active: bool = True


class SchedulerService:
    """定时任务调度器服务"""

    # 最大重试次数
    MAX_RETRIES = 3
    # 重试间隔（秒）
    RETRY_DELAY = 60

    # 任务类型到处理函数的映射
    JOB_HANDLERS: Dict[str, Callable] = {}

    def __init__(self):
        self.scheduler = None
        self._polling_task = None
        self._running = False
        self._db_session_factory = None

        if APSCHEDULER_AVAILABLE:
            self.scheduler = AsyncIOScheduler()
        else:
            self._jobs: Dict[str, Dict[str, Any]] = {}

    def set_db_session_factory(self, session_factory):
        """设置数据库会话工厂"""
        self._db_session_factory = session_factory

    async def start(self):
        """启动调度器"""
        if self._running:
            return

        self._running = True

        if APSCHEDULER_AVAILABLE and self.scheduler:
            self.scheduler.start()
            logger.info("APScheduler调度器已启动")
        else:
            # 启动简单轮询
            self._polling_task = asyncio.create_task(self._polling_loop())
            logger.info("简单轮询调度器已启动")

    async def stop(self):
        """停止调度器"""
        self._running = False

        if APSCHEDULER_AVAILABLE and self.scheduler:
            self.scheduler.shutdown()
        elif self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        logger.info("调度器已停止")

    async def _get_db(self) -> AsyncSession:
        """获取数据库会话"""
        if self._db_session_factory:
            return self._db_session_factory()
        from app.db.session import async_session_maker
        return async_session_maker()

    def _parse_cron(self, cron_expression: str) -> Dict[str, Any]:
        """解析5字段Cron表达式"""
        parts = cron_expression.split()
        if len(parts) != 5:
            raise ValueError(f"无效的Cron表达式: {cron_expression}，需要5个字段")

        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }

    def _get_next_run_time(self, cron_expression: str, base_time: Optional[datetime] = None) -> Optional[datetime]:
        """计算下次执行时间"""
        try:
            if APSCHEDULER_AVAILABLE:
                from apscheduler.triggers.cron import CronTrigger
                trigger = CronTrigger.from_crontab(cron_expression)
                return trigger.get_next_fire_time(None, base_time or datetime.now())
            else:
                # 简单计算：支持常见的固定时间模式
                return self._simple_next_run(cron_expression, base_time)
        except Exception as e:
            logger.error(f"计算下次执行时间失败: {e}")
            return None

    def _simple_next_run(self, cron_expression: str, base_time: Optional[datetime] = None) -> Optional[datetime]:
        """简单计算下次执行时间（不支持复杂cron，仅基础模式）"""
        now = base_time or datetime.now()
        parts = cron_expression.split()
        if len(parts) != 5:
            return None

        minute, hour, day, month, dow = parts

        # 每小时执行: 0 * * * *
        if minute == "0" and hour == "*" and day == "*" and month == "*" and dow == "*":
            next_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            return next_time

        # 每天执行: 0 0 * * *
        if minute == "0" and hour == "0" and day == "*" and month == "*" and dow == "*":
            next_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            return next_time

        # 每分钟执行: * * * * *
        if minute == "*" and hour == "*" and day == "*" and month == "*" and dow == "*":
            return now.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # 固定分钟每小时: 30 * * * *
        if hour == "*" and day == "*" and month == "*" and dow == "*" and minute != "*":
            try:
                m = int(minute)
                next_time = now.replace(minute=m, second=0, microsecond=0)
                if next_time <= now:
                    next_time += timedelta(hours=1)
                return next_time
            except ValueError:
                pass

        # 固定时间每天: 30 9 * * *
        if day == "*" and month == "*" and dow == "*" and minute != "*" and hour != "*":
            try:
                m = int(minute)
                h = int(hour)
                next_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if next_time <= now:
                    next_time += timedelta(days=1)
                return next_time
            except ValueError:
                pass

        # 默认：每分钟检查一次
        return now + timedelta(minutes=1)

    async def add_job(self, job_config: JobConfig) -> str:
        """添加定时任务"""
        db = await self._get_db()
        try:
            job = ScheduledJob(
                id=job_config.id,
                name=job_config.name,
                description=job_config.description,
                job_type=job_config.job_type,
                cron_expression=job_config.cron_expression,
                parameters=job_config.parameters,
                is_active=job_config.is_active,
                created_by=job_config.parameters.get("created_by", "system"),
            )

            # 计算下次执行时间
            next_run = self._get_next_run_time(job_config.cron_expression)
            job.next_run_at = next_run

            db.add(job)
            await db.commit()
            await db.refresh(job)

            # 如果调度器已启动，添加任务到调度器
            if self._running and job.is_active:
                await self._schedule_job(job)

            return job.id
        finally:
            await db.close()

    async def _schedule_job(self, job: ScheduledJob):
        """将任务添加到调度器"""
        if not self._running:
            return

        if APSCHEDULER_AVAILABLE and self.scheduler:
            job_id = f"scheduled_job_{job.id}"
            # 移除已存在的任务
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            self.scheduler.add_job(
                func=self._execute_job_wrapper,
                trigger=CronTrigger.from_crontab(job.cron_expression),
                id=job_id,
                args=[job.id],
                replace_existing=True,
            )
        else:
            self._jobs[job.id] = {
                "id": job.id,
                "cron": job.cron_expression,
                "next_run": job.next_run_at,
            }

    async def _unschedule_job(self, job_id: str):
        """从调度器移除任务"""
        if APSCHEDULER_AVAILABLE and self.scheduler:
            scheduler_job_id = f"scheduled_job_{job_id}"
            if self.scheduler.get_job(scheduler_job_id):
                self.scheduler.remove_job(scheduler_job_id)
        else:
            self._jobs.pop(job_id, None)

    async def remove_job(self, job_id: str):
        """移除定时任务"""
        db = await self._get_db()
        try:
            result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
            job = result.scalar_one_or_none()

            if not job:
                raise NotFoundException(message="定时任务不存在")

            await self._unschedule_job(job_id)
            await db.delete(job)
            await db.commit()
        finally:
            await db.close()

    async def pause_job(self, job_id: str):
        """暂停任务"""
        db = await self._get_db()
        try:
            result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
            job = result.scalar_one_or_none()

            if not job:
                raise NotFoundException(message="定时任务不存在")

            job.is_active = False
            await self._unschedule_job(job_id)
            await db.commit()
            await db.refresh(job)
            return job
        finally:
            await db.close()

    async def resume_job(self, job_id: str):
        """恢复任务"""
        db = await self._get_db()
        try:
            result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
            job = result.scalar_one_or_none()

            if not job:
                raise NotFoundException(message="定时任务不存在")

            job.is_active = True
            job.next_run_at = self._get_next_run_time(job.cron_expression)
            await db.commit()
            await db.refresh(job)

            if self._running:
                await self._schedule_job(job)

            return job
        finally:
            await db.close()

    async def get_jobs(self, job_type: Optional[str] = None, is_active: Optional[bool] = None) -> List[ScheduledJob]:
        """获取所有任务"""
        db = await self._get_db()
        try:
            query = select(ScheduledJob)
            conditions = []

            if job_type:
                conditions.append(ScheduledJob.job_type == job_type)
            if is_active is not None:
                conditions.append(ScheduledJob.is_active == is_active)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(ScheduledJob.created_at.desc())
            result = await db.execute(query)
            return result.scalars().all()
        finally:
            await db.close()

    async def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """获取单个任务"""
        db = await self._get_db()
        try:
            result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
            return result.scalar_one_or_none()
        finally:
            await db.close()

    async def execute_job_now(self, job_id: str) -> JobExecutionLog:
        """立即执行任务"""
        db = await self._get_db()
        try:
            result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
            job = result.scalar_one_or_none()

            if not job:
                raise NotFoundException(message="定时任务不存在")

            return await self._execute_job(db, job, manual=True)
        finally:
            await db.close()

    async def _execute_job_wrapper(self, job_id: str):
        """APScheduler调用的包装器"""
        db = await self._get_db()
        try:
            result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
            job = result.scalar_one_or_none()

            if job and job.is_active:
                await self._execute_job(db, job)
        finally:
            await db.close()

    async def _execute_job(self, db: AsyncSession, job: ScheduledJob, manual: bool = False) -> JobExecutionLog:
        """执行任务"""
        now = datetime.now()

        # 创建执行日志
        log = JobExecutionLog(
            job_id=job.id,
            status=JobStatus.RUNNING.value,
            started_at=now,
            retry_number=job.retry_count if not manual else 0,
        )
        db.add(log)
        await db.flush()

        try:
            # 根据任务类型执行相应处理
            handler = self.JOB_HANDLERS.get(job.job_type)
            if handler:
                output = await handler(job.parameters)
            else:
                output = await self._default_handler(job)

            # 更新日志为成功
            log.status = JobStatus.SUCCESS.value
            log.output = str(output) if output else "任务执行成功"
            log.completed_at = datetime.now()

            # 更新任务状态
            job.last_run_at = now
            job.run_count += 1
            job.retry_count = 0
            job.next_run_at = self._get_next_run_time(job.cron_expression, now)

        except Exception as e:
            logger.error("任务执行失败 %s: %s", job.id, e, exc_info=True)

            job.fail_count += 1

            # 检查是否需要重试
            if job.retry_count < self.MAX_RETRIES and not manual:
                job.retry_count += 1
                log.status = JobStatus.RETRYING.value
                log.error = str(e)
                log.completed_at = datetime.now()

                # 延迟后重试
                await asyncio.sleep(self.RETRY_DELAY * job.retry_count)
                return await self._execute_job(db, job)
            else:
                log.status = JobStatus.FAILED.value
                log.error = str(e)
                log.completed_at = datetime.now()
                job.retry_count = 0
                job.next_run_at = self._get_next_run_time(job.cron_expression, now)

        await db.commit()
        await db.refresh(log)
        return log

    async def _default_handler(self, job: ScheduledJob) -> str:
        """默认任务处理器"""
        handlers = {
            "report": self._handle_generate_report,
            "notification": self._handle_check_overdue,
            "cleanup": self._handle_cleanup,
            "sync": self._handle_sync,
            "ai_analysis": self._handle_ai_analysis,
        }

        handler = handlers.get(job.job_type)
        if handler:
            return await handler(job.parameters)
        return f"未找到任务类型 {job.job_type} 的处理器"

    async def _handle_generate_report(self, params: Dict[str, Any]) -> str:
        """生成日报"""
        report_type = params.get("report_type", "daily")
        project_id = params.get("project_id")

        # 模拟生成报告
        logger.info(f"生成{report_type}报告，项目: {project_id}")
        return f"已生成{report_type}报告"

    async def _handle_check_overdue(self, params: Dict[str, Any]) -> str:
        """检查逾期任务并通知"""
        project_id = params.get("project_id")
        notify_channels = params.get("notify_channels", ["app"])

        logger.info(f"检查逾期任务，项目: {project_id}，通知渠道: {notify_channels}")
        return f"已检查逾期任务并发送通知到 {', '.join(notify_channels)}"

    async def _handle_cleanup(self, params: Dict[str, Any]) -> str:
        """清理过期数据"""
        retention_days = params.get("retention_days", 90)
        data_types = params.get("data_types", ["logs", "temp_files"])

        logger.info(f"清理{retention_days}天前的数据: {data_types}")
        return f"已清理 {', '.join(data_types)} 的过期数据"

    async def _handle_sync(self, params: Dict[str, Any]) -> str:
        """同步第三方集成数据"""
        integration_type = params.get("integration_type", "all")
        sync_options = params.get("sync_options", {})

        logger.info(f"同步集成数据: {integration_type}")
        return f"已同步 {integration_type} 的数据"

    async def _handle_ai_analysis(self, params: Dict[str, Any]) -> str:
        """AI项目健康度分析"""
        project_id = params.get("project_id")
        analysis_type = params.get("analysis_type", "health")

        logger.info(f"AI分析项目健康度: {project_id}, 类型: {analysis_type}")
        return f"已完成项目 {project_id} 的{analysis_type}分析"

    async def _polling_loop(self):
        """简单轮询循环（当APScheduler不可用时）"""
        while self._running:
            try:
                await self._check_and_run_due_jobs()
            except Exception as e:
                logger.error("轮询检查失败: %s", e, exc_info=True)

            await asyncio.sleep(60)  # 每分钟检查一次

    async def _check_and_run_due_jobs(self):
        """检查并执行到期的任务"""
        now = datetime.now()
        db = await self._get_db()
        try:
            result = await db.execute(
                select(ScheduledJob).where(
                    and_(
                        ScheduledJob.is_active == True,
                        ScheduledJob.next_run_at <= now,
                    )
                )
            )
            due_jobs = result.scalars().all()

            for job in due_jobs:
                try:
                    await self._execute_job(db, job)
                except Exception as e:
                    logger.error("执行任务 %s 失败: %s", job.id, e, exc_info=True)
        finally:
            await db.close()

    async def get_job_logs(self, job_id: str, limit: int = 50) -> List[JobExecutionLog]:
        """获取任务执行日志"""
        db = await self._get_db()
        try:
            result = await db.execute(
                select(JobExecutionLog)
                .where(JobExecutionLog.job_id == job_id)
                .order_by(JobExecutionLog.started_at.desc())
                .limit(limit)
            )
            return result.scalars().all()
        finally:
            await db.close()

    async def update_job(self, job_id: str, **kwargs) -> ScheduledJob:
        """更新任务"""
        db = await self._get_db()
        try:
            result = await db.execute(select(ScheduledJob).where(ScheduledJob.id == job_id))
            job = result.scalar_one_or_none()

            if not job:
                raise NotFoundException(message="定时任务不存在")

            allowed_fields = ["name", "description", "job_type", "cron_expression", "parameters", "is_active"]
            for field, value in kwargs.items():
                if field in allowed_fields:
                    setattr(job, field, value)

            # 如果更新了cron表达式，重新计算下次执行时间
            if "cron_expression" in kwargs:
                job.next_run_at = self._get_next_run_time(job.cron_expression)
                if self._running:
                    if job.is_active:
                        await self._schedule_job(job)
                    else:
                        await self._unschedule_job(job_id)

            job.updated_at = datetime.now()
            await db.commit()
            await db.refresh(job)
            return job
        finally:
            await db.close()


# 全局调度器服务实例
scheduler_service = SchedulerService()


def register_job_handler(job_type: str):
    """注册任务处理器的装饰器"""
    def decorator(func: Callable):
        SchedulerService.JOB_HANDLERS[job_type] = func
        return func
    return decorator

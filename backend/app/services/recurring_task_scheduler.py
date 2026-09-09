"""
重复任务调度器服务
使用纯Python datetime计算，不依赖外部调度库
"""

from datetime import datetime, timedelta
from typing import Optional, List
import logging
from calendar import monthrange

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import RecurringTask, RecurringTaskInstance, Task, Project
from app.core.exceptions import NotFoundException, ValidationException


logger = logging.getLogger(__name__)


class RecurringTaskScheduler:
    """重复任务调度器"""

    @staticmethod
    def calculate_next_run(pattern: str, current_date: datetime, **kwargs) -> Optional[datetime]:
        """
        根据模式计算下次运行时间

        Args:
            pattern: 重复模式 (daily/weekly/biweekly/monthly/quarterly/yearly/custom)
            current_date: 当前日期时间
            **kwargs: 额外参数
                - interval_days: 自定义模式间隔天数
                - week_days: 每周模式选中的星期几 [1,3,5] (1=周一, 7=周日)
                - month_day: 每月模式选中的日期

        Returns:
            下次运行时间，如果无法计算则返回None
        """
        if not current_date:
            current_date = datetime.now()

        if pattern == "daily":
            return current_date + timedelta(days=1)

        elif pattern == "weekly":
            week_days = sorted(kwargs.get("week_days", []))
            if not week_days:
                week_days = [1]  # 默认周一

            current_weekday = current_date.weekday() + 1  # 转换为1-7 (周一=1)

            # 查找下一个选中的星期几
            for wd in week_days:
                if wd > current_weekday:
                    days_diff = wd - current_weekday
                    return current_date + timedelta(days=days_diff)

            # 如果本周没有更晚的选中日期，跳到下周第一个
            days_diff = (7 - current_weekday) + week_days[0]
            return current_date + timedelta(days=days_diff)

        elif pattern == "biweekly":
            return current_date + timedelta(weeks=2)

        elif pattern == "monthly":
            month_day = kwargs.get("month_day", 1)
            year = current_date.year
            month = current_date.month

            # 尝试本月
            if month_day >= current_date.day:
                _, last_day = monthrange(year, month)
                day = min(month_day, last_day)
                next_date = current_date.replace(day=day)
                if next_date > current_date:
                    return next_date

            # 下个月
            month += 1
            if month > 12:
                month = 1
                year += 1
            _, last_day = monthrange(year, month)
            day = min(month_day, last_day)
            return current_date.replace(year=year, month=month, day=day)

        elif pattern == "quarterly":
            # 每3个月
            month = current_date.month
            year = current_date.year

            quarter_months = [3, 6, 9, 12]
            for qm in quarter_months:
                if qm > month:
                    _, last_day = monthrange(year, qm)
                    day = min(current_date.day, last_day)
                    return current_date.replace(month=qm, day=day)

            # 下一年第一季度
            _, last_day = monthrange(year + 1, 3)
            day = min(current_date.day, last_day)
            return current_date.replace(year=year + 1, month=3, day=day)

        elif pattern == "yearly":
            year = current_date.year + 1
            try:
                return current_date.replace(year=year)
            except ValueError:
                # 处理闰年2月29日的情况
                if current_date.month == 2 and current_date.day == 29:
                    return current_date.replace(year=year, day=28)
                raise

        elif pattern == "custom":
            interval_days = kwargs.get("interval_days", 1)
            return current_date + timedelta(days=interval_days)

        return None

    @staticmethod
    def generate_next_occurrence(recurring_task: RecurringTask) -> Optional[datetime]:
        """
        计算重复任务的下次执行时间

        Args:
            recurring_task: 重复任务规则对象

        Returns:
            下次执行时间
        """
        base_date = recurring_task.last_run_at or recurring_task.created_at or datetime.now()

        kwargs = {}
        if recurring_task.pattern == "weekly":
            kwargs["week_days"] = recurring_task.week_days or [1]
        elif recurring_task.pattern == "monthly":
            kwargs["month_day"] = recurring_task.month_day or 1
        elif recurring_task.pattern == "custom":
            kwargs["interval_days"] = recurring_task.interval_days or 1

        next_run = RecurringTaskScheduler.calculate_next_run(
            recurring_task.pattern,
            base_date,
            **kwargs
        )

        return next_run

    @staticmethod
    def should_end(recurring_task: RecurringTask) -> bool:
        """
        检查重复任务是否应该结束

        Args:
            recurring_task: 重复任务规则对象

        Returns:
            是否应该结束
        """
        if recurring_task.end_condition == "never":
            return False

        if recurring_task.end_condition == "after_count":
            return recurring_task.run_count >= recurring_task.end_after_count

        if recurring_task.end_condition == "on_date":
            if recurring_task.end_date:
                return datetime.now() >= recurring_task.end_date
            return False

        return False

    @staticmethod
    async def create_instance(
        db: AsyncSession,
        recurring_task: RecurringTask,
        commit: bool = True,
    ) -> Task:
        """
        根据重复规则创建任务实例

        Args:
            db: 数据库会话
            recurring_task: 重复任务规则对象

        Returns:
            创建的任务实例
        """
        # 获取基础任务信息
        base_task = None
        if recurring_task.base_task_id:
            result = await db.execute(
                select(Task).where(Task.id == recurring_task.base_task_id)
            )
            base_task = result.scalar_one_or_none()

        # 构建任务名称
        sequence = (recurring_task.run_count or 0) + 1
        if base_task:
            task_name = f"{base_task.name} (重复 #{sequence})"
            description = base_task.description or ""
            priority = base_task.priority
            estimated_hours = float(base_task.estimated_hours) if base_task.estimated_hours else 0
            assignee_id = base_task.assignee_id
            labels = base_task.labels or []
            category = base_task.category
        else:
            task_name = f"重复任务 #{sequence}"
            description = "由重复规则生成的任务"
            priority = 3
            estimated_hours = 0
            assignee_id = None
            labels = ["recurring"]
            category = None

        # 计算计划日期
        now = datetime.now()
        planned_start = now
        planned_end = now + timedelta(days=1)

        # 创建任务
        task = Task(
            project_id=recurring_task.project_id,
            name=task_name,
            description=description,
            priority=priority,
            estimated_hours=estimated_hours,
            assignee_id=assignee_id,
            labels=labels,
            category=category,
            status="todo",
            planned_start=planned_start,
            planned_end=planned_end,
        )

        try:
            db.add(task)
            await db.flush()  # 获取 task.id

            # 创建实例记录
            instance = RecurringTaskInstance(
                recurring_task_id=recurring_task.id,
                task_id=task.id,
                sequence_number=sequence,
            )
            db.add(instance)

            # 更新重复任务状态
            recurring_task.run_count = sequence
            recurring_task.last_run_at = now
            recurring_task.next_run_at = RecurringTaskScheduler.generate_next_occurrence(recurring_task)

            if commit:
                # 单实例场景（run_now 等）：父任务计数/next_run 与子实例（Task + RecurringTaskInstance）
                # 在同一事务内提交，要么全部成功要么整体回滚；回滚立即释放连接，
                # 不在重试/睡眠期间持有（符合 F6 备注：避免 ~180s 连接占用）
                await db.commit()
                await db.refresh(task)
            # commit=False：仅 flush，由调用方（process_due_tasks）统一提交，实现批级事务隔离
        except Exception:
            if commit:
                # 单实例提交失败：原子回滚并释放连接
                await db.rollback()
            # commit=False 时不在函数内回滚，交由外层事务统一回滚（批级原子性）
            raise

        return task

    @staticmethod
    async def process_due_tasks(db: AsyncSession) -> List[Task]:
        """
        处理所有到期的重复任务。

        批级事务隔离（F9）：母任务状态更新（run_count / next_run_at / is_active）与所有子实例
        （Task + RecurringTaskInstance）在【单个 DB 事务】内完成——任一失败则整体回滚，
        要么全成功，要么全回滚，避免出现父/子部分写入的不一致。
        """
        now = datetime.now()

        result = await db.execute(
            select(RecurringTask).where(
                RecurringTask.is_active == True,
                RecurringTask.next_run_at <= now
            )
        )
        due_tasks = result.scalars().all()

        created_instances: List[Task] = []

        try:
            for rt in due_tasks:
                if RecurringTaskScheduler.should_end(rt):
                    rt.is_active = False
                    continue
                # commit=False：子调用内不提交，统一由本事务在循环结束后一次性提交
                task = await RecurringTaskScheduler.create_instance(db, rt, commit=False)
                created_instances.append(task)
            # 单个事务提交：所有母任务状态 + 子实例原子落库
            await db.commit()
        except Exception as e:
            # 整体回滚：当前批次任一任务失败，已 flush 的父/子写入全部撤销
            await db.rollback()
            logger.error("重复任务批量创建失败，已整体回滚: %s", e, exc_info=True)
            raise

        return created_instances

    @staticmethod
    async def run_now(db: AsyncSession, recurring_task_id: str) -> Task:
        """
        立即执行一次重复任务

        Args:
            db: 数据库会话
            recurring_task_id: 重复任务ID

        Returns:
            创建的任务实例
        """
        result = await db.execute(
            select(RecurringTask).where(RecurringTask.id == recurring_task_id)
        )
        recurring_task = result.scalar_one_or_none()

        if not recurring_task:
            raise NotFoundException(message="重复任务不存在")

        if RecurringTaskScheduler.should_end(recurring_task):
            raise ValidationException(message="重复任务已结束")

        task = await RecurringTaskScheduler.create_instance(db, recurring_task)
        return task

    @staticmethod
    def preview_next_runs(
        pattern: str,
        start_date: datetime,
        count: int = 5,
        **kwargs
    ) -> List[datetime]:
        """
        预览未来N次执行时间

        Args:
            pattern: 重复模式
            start_date: 开始日期
            count: 预览次数
            **kwargs: 额外参数

        Returns:
            未来执行时间列表
        """
        dates: List[datetime] = []
        current = start_date

        for _ in range(count):
            next_run = RecurringTaskScheduler.calculate_next_run(pattern, current, **kwargs)
            if next_run:
                dates.append(next_run)
                current = next_run
            else:
                break

        return dates

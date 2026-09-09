from typing import Dict, Any, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.automation import AutomationRule
from app.models import Task
from app.services.automation_engine import AutomationEngine


class AutomationTriggerService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.engine = AutomationEngine(db)

    async def on_task_created(self, task: Task, trigger_data: Optional[Dict[str, Any]] = None) -> None:
        await self._evaluate_rules(
            trigger_type="task_created",
            entity=task,
            trigger_data=trigger_data or self._task_to_dict(task)
        )

    async def on_task_updated(
        self,
        task: Task,
        old_values: Optional[Dict[str, Any]] = None,
        trigger_data: Optional[Dict[str, Any]] = None
    ) -> None:
        data = trigger_data or self._task_to_dict(task)
        if old_values:
            data["old_values"] = old_values
            data["changed_fields"] = list(old_values.keys())

        await self._evaluate_rules(
            trigger_type="task_updated",
            entity=task,
            trigger_data=data
        )

    async def on_status_changed(
        self,
        task: Task,
        old_status: str,
        new_status: str,
        trigger_data: Optional[Dict[str, Any]] = None
    ) -> None:
        data = trigger_data or self._task_to_dict(task)
        data["old_status"] = old_status
        data["new_status"] = new_status

        await self._evaluate_rules(
            trigger_type="status_changed",
            entity=task,
            trigger_data=data
        )

    async def on_due_date_approaching(
        self,
        task: Task,
        days_remaining: int,
        trigger_data: Optional[Dict[str, Any]] = None
    ) -> None:
        data = trigger_data or self._task_to_dict(task)
        data["days_remaining"] = days_remaining

        await self._evaluate_rules(
            trigger_type="due_date_approaching",
            entity=task,
            trigger_data=data
        )

    async def _evaluate_rules(
        self,
        trigger_type: str,
        entity: Any,
        trigger_data: Dict[str, Any]
    ) -> None:
        project_id = None
        if hasattr(entity, "project_id"):
            project_id = entity.project_id

        rules = await self.engine.get_matching_rules(trigger_type, project_id)

        for rule in rules:
            try:
                triggered = await self.engine.evaluate_trigger(rule, entity, trigger_data)
                if triggered:
                    await self.engine.execute_actions(rule, entity, trigger_data)
            except Exception:
                continue

    def _task_to_dict(self, task: Task) -> Dict[str, Any]:
        return {
            "id": task.id,
            "project_id": task.project_id,
            "name": task.name,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "assignee_id": task.assignee_id,
            "progress": float(task.progress) if task.progress else 0,
            "planned_start": task.planned_start.isoformat() if task.planned_start else None,
            "planned_end": task.planned_end.isoformat() if task.planned_end else None,
            "labels": task.labels or [],
            "category": task.category,
        }


async def trigger_task_created(db: AsyncSession, task: Task) -> None:
    service = AutomationTriggerService(db)
    await service.on_task_created(task)


async def trigger_task_updated(
    db: AsyncSession,
    task: Task,
    old_values: Optional[Dict[str, Any]] = None
) -> None:
    service = AutomationTriggerService(db)
    await service.on_task_updated(task, old_values)


async def trigger_status_changed(
    db: AsyncSession,
    task: Task,
    old_status: str,
    new_status: str
) -> None:
    service = AutomationTriggerService(db)
    await service.on_status_changed(task, old_status, new_status)


async def trigger_due_date_approaching(
    db: AsyncSession,
    task: Task,
    days_remaining: int
) -> None:
    service = AutomationTriggerService(db)
    await service.on_due_date_approaching(task, days_remaining)

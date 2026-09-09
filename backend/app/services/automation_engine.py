from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
import operator

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models.automation import AutomationRule
from app.models import Task, User, Project, Notification
from app.core.exceptions import BusinessException
from app.config import settings


class AutomationEngine:
    OPERATORS = {
        "field_equals": operator.eq,
        "field_contains": lambda a, b: b in str(a) if a is not None else False,
        "field_greater_than": operator.gt,
        "field_less_than": operator.lt,
        "field_in_list": lambda a, b: a in b if isinstance(b, list) else False,
    }

    def __init__(self, db: AsyncSession):
        self.db = db
        self.execution_log: List[Dict[str, Any]] = []
        self.errors: List[str] = []

    async def evaluate_trigger(
        self,
        rule: AutomationRule,
        entity: Any,
        trigger_data: Dict[str, Any]
    ) -> bool:
        conditions = rule.trigger_conditions
        if not conditions:
            return True

        return self._evaluate_conditions(conditions, entity, trigger_data)

    def _evaluate_conditions(
        self,
        conditions: Dict[str, Any],
        entity: Any,
        trigger_data: Dict[str, Any]
    ) -> bool:
        if "operator" in conditions and "conditions" in conditions:
            op = conditions["operator"]
            sub_conditions = conditions["conditions"]
            results = [
                self._evaluate_conditions(c, entity, trigger_data)
                for c in sub_conditions
            ]
            if op == "AND":
                return all(results)
            elif op == "OR":
                return any(results)
            return False

        field = conditions.get("field")
        op_key = conditions.get("operator")
        value = conditions.get("value")

        if not field or not op_key:
            return True

        entity_value = self._get_field_value(field, entity, trigger_data)
        op_func = self.OPERATORS.get(op_key)

        if op_func is None:
            return False

        try:
            return op_func(entity_value, value)
        except Exception:
            return False

    def _get_field_value(
        self,
        field: str,
        entity: Any,
        trigger_data: Dict[str, Any]
    ) -> Any:
        if field.startswith("trigger."):
            trigger_field = field.replace("trigger.", "")
            return trigger_data.get(trigger_field)

        if trigger_data and field in trigger_data:
            return trigger_data.get(field)

        if hasattr(entity, field):
            return getattr(entity, field)

        if isinstance(entity, dict):
            return entity.get(field)

        return None

    async def execute_actions(
        self,
        rule: AutomationRule,
        entity: Any,
        trigger_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        self.execution_log = []
        self.errors = []

        for action in rule.actions:
            try:
                result = await self._execute_action(action, entity, trigger_data)
                self.execution_log.append({
                    "action": action,
                    "result": result,
                    "success": True,
                })
            except Exception as e:
                self.errors.append(str(e))
                self.execution_log.append({
                    "action": action,
                    "error": str(e),
                    "success": False,
                })

        return self.execution_log

    async def _execute_action(
        self,
        action: Dict[str, Any],
        entity: Any,
        trigger_data: Dict[str, Any]
    ) -> Any:
        action_type = action.get("type")
        # 兼容两种 action 结构：参数嵌套在 params 里，或直接放在 action 顶层
        params = action.get("params")
        if not params:
            params = {k: v for k, v in action.items() if k != "type"}

        if action_type == "update_field":
            return await self._action_update_field(params, entity)
        elif action_type == "send_notification":
            return await self._action_send_notification(params, entity)
        elif action_type == "create_task":
            return await self._action_create_task(params, entity, trigger_data)
        elif action_type == "assign_task":
            return await self._action_assign_task(params, entity)
        elif action_type == "send_email":
            return await self._action_send_email(params, entity)
        elif action_type == "add_label":
            return await self._action_add_label(params, entity)
        elif action_type == "move_status":
            return await self._action_move_status(params, entity)

        raise BusinessException(message=f"未知动作类型: {action_type}")

    async def _action_update_field(self, params: Dict[str, Any], entity: Any) -> Dict[str, Any]:
        field = params.get("field")
        value = params.get("value")

        if not field or not hasattr(entity, field):
            raise BusinessException(message=f"字段不存在: {field}")

        setattr(entity, field, value)
        entity.updated_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(entity)

        return {"field": field, "value": value}

    async def _action_send_notification(self, params: Dict[str, Any], entity: Any) -> Dict[str, Any]:
        title = params.get("title", "自动化通知")
        message = params.get("message") or params.get("content", "")
        recipients = params.get("recipients", []) or []

        # 渲染简单模板 {{task.name}} / {{entity.field}} -> 实际值
        def _render(text: str) -> str:
            if not text or "{{" not in text:
                return text
            import re
            def _repl(m):
                expr = m.group(1).strip()
                if "." in expr:
                    obj_key, field = expr.split(".", 1)
                    obj = entity if obj_key in ("task", "entity", "project") else None
                    if obj is not None and hasattr(obj, field):
                        return str(getattr(obj, field) or "")
                if hasattr(entity, expr):
                    return str(getattr(entity, expr) or "")
                return m.group(0)
            return re.sub(r"\{\{([^}]+)\}\}", _repl, text)

        title = _render(title)
        message = _render(message)

        # 未显式指定接收人时，默认通知任务负责人，确保自动化真正触达用户（数据打通）
        if not recipients and getattr(entity, "assignee_id", None):
            recipients = [entity.assignee_id]

        related_type = "task" if hasattr(entity, "project_id") else None
        related_id = getattr(entity, "id", None)

        created_recipients = []
        for recipient in recipients:
            notification = Notification(
                user_id=str(recipient),
                type="automation",
                title=title,
                content=message,
                related_type=related_type,
                related_id=str(related_id) if related_id else None,
            )
            self.db.add(notification)
            created_recipients.append(str(recipient))

        # 同时通过 Webhook 推送通知事件，打通外部系统
        try:
            from app.services.webhook_service import trigger_webhook_event
            await trigger_webhook_event(
                self.db,
                "notification.created",
                {
                    "event": "notification.created",
                    "data": {
                        "title": title,
                        "message": message,
                        "recipients": recipients,
                    },
                },
            )
        except Exception as e:
            logger.warning("自动化通知 Webhook 推送失败（已忽略）: %s", e, exc_info=True)

        await self.db.commit()
        return {
            "type": "notification",
            "title": title,
            "message": message,
            "recipients": created_recipients,
        }

    async def _action_create_task(
        self,
        params: Dict[str, Any],
        entity: Any,
        trigger_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        project_id = params.get("project_id")
        if not project_id and hasattr(entity, "project_id"):
            project_id = entity.project_id

        if not project_id:
            raise BusinessException(message="缺少项目ID")

        task = Task(
            project_id=project_id,
            name=params.get("name", "自动化创建任务"),
            description=params.get("description", ""),
            status=params.get("status", "todo"),
            priority=params.get("priority", 3),
            assignee_id=params.get("assignee_id"),
            planned_start=datetime.now(),
            planned_end=datetime.now() + timedelta(days=params.get("due_days", 7)),
        )

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        return {"task_id": task.id, "name": task.name}

    async def _action_assign_task(self, params: Dict[str, Any], entity: Any) -> Dict[str, Any]:
        assignee_id = params.get("assignee_id")

        if not assignee_id:
            raise BusinessException(message="缺少负责人ID")

        if not hasattr(entity, "assignee_id"):
            raise BusinessException(message="实体不支持分配")

        entity.assignee_id = assignee_id
        entity.updated_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(entity)

        return {"assignee_id": assignee_id}

    async def _action_send_email(self, params: Dict[str, Any], entity: Any) -> Dict[str, Any]:
        to = params.get("to", []) or []
        subject = params.get("subject", "")
        body = params.get("body", "")

        result = {"type": "email", "to": to, "subject": subject, "sent": False}
        try:
            from app.core.email import send_email as _send_email
            email_result = await _send_email(to=to, subject=subject, body=body)
            result["sent"] = email_result.get("success", False)
        except Exception as e:
            result["error"] = str(e)
            logger.warning(f"自动化邮件发送失败: {e}")
        return result

    async def _action_add_label(self, params: Dict[str, Any], entity: Any) -> Dict[str, Any]:
        label = params.get("label")

        if not label:
            raise BusinessException(message="缺少标签")

        if not hasattr(entity, "labels"):
            raise BusinessException(message="实体不支持标签")

        labels = list(entity.labels or [])
        if label not in labels:
            labels.append(label)
            entity.labels = labels
            entity.updated_at = datetime.now()
            await self.db.commit()
            await self.db.refresh(entity)

        return {"labels": entity.labels}

    async def _action_move_status(self, params: Dict[str, Any], entity: Any) -> Dict[str, Any]:
        status = params.get("status")

        if not status:
            raise BusinessException(message="缺少目标状态")

        if not hasattr(entity, "status"):
            raise BusinessException(message="实体不支持状态")

        entity.status = status
        entity.updated_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(entity)

        return {"status": status}

    async def get_matching_rules(
        self,
        trigger_type: str,
        project_id: Optional[str] = None
    ) -> List[AutomationRule]:
        query = select(AutomationRule).where(
            AutomationRule.trigger_type == trigger_type,
            AutomationRule.is_active == True
        )

        if project_id:
            query = query.where(
                or_(
                    AutomationRule.project_id == project_id,
                    AutomationRule.is_global == True
                )
            )

        result = await self.db.execute(query)
        return result.scalars().all()

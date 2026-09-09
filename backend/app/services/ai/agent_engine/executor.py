"""
PMI中国AI项目管理社区 - AI Agent执行引擎核心
支持自然语言指令解析和真实业务操作执行

[CPMAI Phase: CPMAI Phase: Model Development | Domain: AI Management — AI Agent核心执行引擎]"""

import json
import re
from typing import Dict, Any, List, Optional, AsyncIterator
from datetime import datetime, date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from app.core.ai_engine import ai_engine
import logging

logger = logging.getLogger(__name__)
from app.models import (
    Task, Project, User, Comment, Notification, AgentSession,
    TaskStatus, TaskPriority
)
from app.services.notification_service import create_notification


INTENT_RECOGNITION_PROMPT = """你是PMI中国AI项目管理社区的Agent意图识别引擎。
请分析用户的自然语言指令，识别意图并提取关键参数。

支持的操作类型：
- create_task: 创建任务（需要：任务名称、项目ID、负责人、截止日期等）
- update_task: 更新任务状态/进度/负责人（需要：任务ID或名称、更新字段）
- assign_task: 分配任务给某人（需要：任务ID或名称、负责人）
- query_tasks: 查询任务（需要：查询条件）
- create_project: 创建项目（需要：项目名称、描述等）
- add_comment: 添加评论（需要：任务ID、评论内容）
- generate_report: 生成报告（需要：项目ID、报告类型）
- send_notification: 发送通知（需要：接收人、标题、内容）
- schedule_meeting: 安排会议/创建会议任务（需要：会议主题、时间、参与人）
- unknown: 无法识别的意图

用户指令：{text}
当前项目ID：{project_id}
当前用户ID：{user_id}

请严格按照以下JSON格式输出（只输出纯JSON，不要任何markdown）：
{{
    "action_type": "操作类型",
    "confidence": 0.95,
    "parameters": {{
        "参数名": "参数值"
    }},
    "missing_required": ["缺失的必填参数"],
    "clarification_needed": false,
    "clarification_question": ""
}}

要求：
1. 准确识别用户意图
2. 提取所有可能的参数
3. 如果缺少必填参数，设置clarification_needed为true并提供澄清问题
4. 日期格式统一为ISO格式
5. 只输出JSON"""


AGENT_SYSTEM_PROMPT = """你是PMI中国AI项目管理社区的智能Agent助手。
你可以直接执行项目管理操作，包括创建任务、更新状态、分配任务、查询数据等。

执行操作时要：
1. 确认用户意图
2. 提取关键参数
3. 执行对应操作
4. 反馈执行结果

请用中文回复，保持专业、简洁。如果操作失败，说明原因并提供建议。"""


class AgentEngine:
    """AI Agent执行引擎"""

    def __init__(self, provider_name: Optional[str] = None):
        self.provider_name = provider_name
        self.engine = ai_engine

    async def execute_natural_language(
        self,
        db: AsyncSession,
        user_id: str,
        project_id: Optional[str],
        text: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行自然语言指令
        步骤：
        1. 解析用户意图
        2. 提取关键参数
        3. 执行对应操作
        4. 生成执行结果反馈
        """
        executed_steps = []

        # 步骤1：解析用户意图
        step1_result = await self._parse_intent(text, project_id, user_id)
        executed_steps.append({"step": "意图识别", "result": step1_result})

        action_type = step1_result.get("action_type", "unknown")
        confidence = step1_result.get("confidence", 0)
        parameters = step1_result.get("parameters", {})

        # 如果缺少必填参数，返回澄清请求
        if step1_result.get("clarification_needed"):
            return {
                "success": False,
                "action_type": action_type,
                "executed_steps": executed_steps,
                "result": None,
                "message": step1_result.get("clarification_question", "需要更多信息才能执行此操作"),
                "clarification_needed": True,
            }

        # 步骤2 & 3：执行对应操作
        try:
            if action_type == "create_task":
                result = await self._execute_create_task(db, user_id, project_id, parameters)
            elif action_type == "update_task":
                result = await self._execute_update_task(db, user_id, parameters)
            elif action_type == "assign_task":
                result = await self._execute_assign_task(db, user_id, parameters)
            elif action_type == "query_tasks":
                result = await self._execute_query_tasks(db, user_id, project_id, parameters)
            elif action_type == "create_project":
                result = await self._execute_create_project(db, user_id, parameters)
            elif action_type == "add_comment":
                result = await self._execute_add_comment(db, user_id, parameters)
            elif action_type == "generate_report":
                result = await self._execute_generate_report(db, user_id, project_id, parameters)
            elif action_type == "send_notification":
                result = await self._execute_send_notification(db, user_id, parameters)
            elif action_type == "schedule_meeting":
                result = await self._execute_schedule_meeting(db, user_id, project_id, parameters)
            else:
                result = {
                    "success": False,
                    "error": f"不支持的操作类型: {action_type}",
                }

            executed_steps.append({"step": "执行操作", "result": result})

            if result.get("success"):
                return {
                    "success": True,
                    "action_type": action_type,
                    "executed_steps": executed_steps,
                    "result": result.get("data"),
                    "message": result.get("message", "操作执行成功"),
                }
            else:
                return {
                    "success": False,
                    "action_type": action_type,
                    "executed_steps": executed_steps,
                    "result": None,
                    "message": result.get("error", "操作执行失败"),
                }

        except Exception as e:
            executed_steps.append({"step": "执行操作", "result": {"error": str(e)}})
            return {
                "success": False,
                "action_type": action_type,
                "executed_steps": executed_steps,
                "result": None,
                "message": f"执行过程中发生错误: {str(e)}",
            }

    async def _parse_intent(
        self,
        text: str,
        project_id: Optional[str],
        user_id: str
    ) -> Dict[str, Any]:
        """使用LLM解析用户意图"""
        prompt = INTENT_RECOGNITION_PROMPT.format(
            text=text,
            project_id=project_id or "未指定",
            user_id=user_id,
        )

        try:
            response = await self.engine.generate(
                prompt,
                provider=self.provider_name,
                temperature=0.1,
                max_tokens=1000
            )
            result = self._safe_json_loads(response)
        except Exception:
            result = {}

        if not result or "action_type" not in result:
            # 本地规则兜底
            result = self._rule_based_intent_recognition(text)

        return result

    def _rule_based_intent_recognition(self, text: str) -> Dict[str, Any]:
        """基于规则的意图识别（兜底方案）"""
        text_lower = text.lower()

        # 创建任务
        if any(kw in text_lower for kw in ["创建任务", "新建任务", "添加任务", "增加任务", "新建一个任务"]):
            params = {}
            name_match = re.search(r'["\']([^"\']+)["\']', text)
            if name_match:
                params["name"] = name_match.group(1)
            else:
                name_match = re.search(r'(?:任务|叫做|名为|名称是)\s*[:：]?\s*([^，,。；;\n]+)', text)
                if name_match:
                    params["name"] = name_match.group(1).strip()

            assignee_match = re.search(r'(?:分配给|负责人|指派给|交给)\s*[:：]?\s*([^，,。；;\n]+)', text)
            if assignee_match:
                params["assignee_name"] = assignee_match.group(1).strip()

            return {
                "action_type": "create_task",
                "confidence": 0.7,
                "parameters": params,
                "missing_required": ["name"] if "name" not in params else [],
                "clarification_needed": "name" not in params,
                "clarification_question": "请提供任务名称",
            }

        # 更新任务
        if any(kw in text_lower for kw in ["更新任务", "修改任务", "更改任务", "任务状态", "进度更新"]):
            params = {}
            name_match = re.search(r'["\x27]([^"\x27]+)["\x27]', text)
            if name_match:
                params["task_name"] = name_match.group(1)

            status_match = re.search(r'(?:状态改为|状态设置为|更新为|改为)\s*[:：]?\s*(\w+)', text)
            if status_match:
                params["status"] = status_match.group(1)

            return {
                "action_type": "update_task",
                "confidence": 0.7,
                "parameters": params,
                "missing_required": [],
                "clarification_needed": False,
                "clarification_question": "",
            }

        # 分配任务
        if any(kw in text_lower for kw in ["分配任务", "指派任务", "交给", "分配给"]):
            params = {}
            name_match = re.search(r'["\x27]([^"\x27]+)["\x27]', text)
            if name_match:
                params["task_name"] = name_match.group(1)

            assignee_match = re.search(r'(?:分配给|指派给|交给)\s*[:：]?\s*([^，,。；;\n]+)', text)
            if assignee_match:
                params["assignee_name"] = assignee_match.group(1).strip()

            return {
                "action_type": "assign_task",
                "confidence": 0.7,
                "parameters": params,
                "missing_required": [],
                "clarification_needed": False,
                "clarification_question": "",
            }

        # 查询任务
        if any(kw in text_lower for kw in ["查询任务", "查看任务", "任务列表", "有哪些任务", "显示任务"]):
            return {
                "action_type": "query_tasks",
                "confidence": 0.7,
                "parameters": {},
                "missing_required": [],
                "clarification_needed": False,
                "clarification_question": "",
            }

        # 创建项目
        if any(kw in text_lower for kw in ["创建项目", "新建项目", "添加项目", "新项目"]):
            params = {}
            name_match = re.search(r'["\x27]([^"\x27]+)["\x27]', text)
            if name_match:
                params["name"] = name_match.group(1)
            else:
                name_match = re.search(r'(?:项目|叫做|名为|名称是)\s*[:：]?\s*([^，,。；;\n]+)', text)
                if name_match:
                    params["name"] = name_match.group(1).strip()

            return {
                "action_type": "create_project",
                "confidence": 0.7,
                "parameters": params,
                "missing_required": ["name"] if "name" not in params else [],
                "clarification_needed": "name" not in params,
                "clarification_question": "请提供项目名称",
            }

        # 添加评论
        if any(kw in text_lower for kw in ["添加评论", "写评论", "评论", "备注"]):
            params = {"content": text}
            return {
                "action_type": "add_comment",
                "confidence": 0.6,
                "parameters": params,
                "missing_required": [],
                "clarification_needed": False,
                "clarification_question": "",
            }

        # 生成报告
        if any(kw in text_lower for kw in ["生成报告", "报告", "统计", "汇总"]):
            return {
                "action_type": "generate_report",
                "confidence": 0.7,
                "parameters": {},
                "missing_required": [],
                "clarification_needed": False,
                "clarification_question": "",
            }

        # 安排会议
        if any(kw in text_lower for kw in ["安排会议", "创建会议", "开会", "会议"]):
            params = {}
            name_match = re.search(r'["\x27]([^"\x27]+)["\x27]', text)
            if name_match:
                params["name"] = name_match.group(1)

            return {
                "action_type": "schedule_meeting",
                "confidence": 0.7,
                "parameters": params,
                "missing_required": [],
                "clarification_needed": False,
                "clarification_question": "",
            }

        return {
            "action_type": "unknown",
            "confidence": 0,
            "parameters": {},
            "missing_required": [],
            "clarification_needed": True,
            "clarification_question": "我不太理解您的指令。您可以尝试说：'创建一个任务'、'查询所有任务'、'分配任务给张三'等。",
        }

    def _safe_json_loads(self, text: str) -> Dict[str, Any]:
        """安全解析JSON"""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)

        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {}

    async def _find_user_by_name(self, db: AsyncSession, name: str) -> Optional[User]:
        """通过用户名查找用户"""
        result = await db.execute(
            select(User).where(
                (User.username == name) | (User.full_name == name) | (User.email == name)
            )
        )
        return result.scalar_one_or_none()

    async def _find_task_by_name_or_id(
        self, db: AsyncSession, project_id: Optional[str], name_or_id: str
    ) -> Optional[Task]:
        """通过任务名或ID查找任务"""
        # 先按ID查找
        result = await db.execute(
            select(Task).where(Task.id == name_or_id, Task.is_deleted == False)
        )
        task = result.scalar_one_or_none()
        if task:
            return task

        # 再按名称查找
        query = select(Task).where(
            Task.name.ilike(f"%{name_or_id}%"),
            Task.is_deleted == False
        )
        if project_id:
            query = query.where(Task.project_id == project_id)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def _execute_create_task(
        self,
        db: AsyncSession,
        user_id: str,
        project_id: Optional[str],
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行创建任务"""
        name = parameters.get("name") or parameters.get("task_name")
        if not name:
            return {"success": False, "error": "任务名称不能为空"}

        target_project_id = parameters.get("project_id") or project_id
        if not target_project_id:
            return {"success": False, "error": "未指定项目ID"}

        # 验证项目存在
        project_result = await db.execute(
            select(Project).where(Project.id == target_project_id, Project.is_deleted == False)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            return {"success": False, "error": "项目不存在"}

        # 计算WBS编码
        sibling_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == target_project_id,
                Task.parent_task_id == None,
                Task.is_deleted == False
            )
        )
        sibling_count = sibling_result.scalar() + 1
        wbs_code = str(sibling_count)

        # 处理负责人
        assignee_id = parameters.get("assignee_id")
        if not assignee_id and parameters.get("assignee_name"):
            user = await self._find_user_by_name(db, parameters.get("assignee_name"))
            if user:
                assignee_id = user.id

        # 处理截止日期
        planned_end = None
        if parameters.get("due_date"):
            try:
                planned_end = datetime.fromisoformat(parameters.get("due_date").replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        if not planned_end and parameters.get("planned_end"):
            try:
                planned_end = datetime.fromisoformat(parameters.get("planned_end").replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        # 处理优先级
        priority = TaskPriority.MEDIUM.value
        if parameters.get("priority"):
            try:
                p = int(parameters.get("priority"))
                if 1 <= p <= 5:
                    priority = p
            except (ValueError, TypeError):
                pass

        task = Task(
            project_id=target_project_id,
            wbs_code=wbs_code,
            name=name,
            description=parameters.get("description"),
            priority=priority,
            status=parameters.get("status", TaskStatus.TODO.value),
            assignee_id=assignee_id,
            planned_end=planned_end,
            labels=parameters.get("labels", []),
            category=parameters.get("category"),
        )

        db.add(task)
        await db.commit()
        await db.refresh(task)

        return {
            "success": True,
            "message": f"任务 '{name}' 创建成功",
            "data": {
                "task_id": task.id,
                "name": task.name,
                "wbs_code": task.wbs_code,
                "project_id": task.project_id,
                "status": task.status,
                "assignee_id": task.assignee_id,
            }
        }

    async def _execute_update_task(
        self,
        db: AsyncSession,
        user_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行更新任务"""
        task_id = parameters.get("task_id")
        task_name = parameters.get("task_name") or parameters.get("name")

        task = None
        if task_id:
            result = await db.execute(
                select(Task).where(Task.id == task_id, Task.is_deleted == False)
            )
            task = result.scalar_one_or_none()
        elif task_name:
            result = await db.execute(
                select(Task).where(Task.name.ilike(f"%{task_name}%"), Task.is_deleted == False)
            )
            task = result.scalar_one_or_none()

        if not task:
            return {"success": False, "error": "未找到指定任务"}

        update_fields = {}
        if "status" in parameters:
            update_fields["status"] = parameters["status"]
        if "progress" in parameters:
            try:
                progress = float(parameters["progress"])
                update_fields["progress"] = max(0, min(100, progress))
            except (ValueError, TypeError):
                pass
        if "priority" in parameters:
            try:
                priority = int(parameters["priority"])
                if 1 <= priority <= 5:
                    update_fields["priority"] = priority
            except (ValueError, TypeError):
                pass
        if "name" in parameters and parameters["name"]:
            update_fields["name"] = parameters["name"]
        if "description" in parameters:
            update_fields["description"] = parameters["description"]
        if "assignee_id" in parameters:
            update_fields["assignee_id"] = parameters["assignee_id"]
        if "assignee_name" in parameters:
            user = await self._find_user_by_name(db, parameters["assignee_name"])
            if user:
                update_fields["assignee_id"] = user.id
        if "planned_end" in parameters and parameters["planned_end"]:
            try:
                update_fields["planned_end"] = datetime.fromisoformat(
                    parameters["planned_end"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass
        if "due_date" in parameters and parameters["due_date"]:
            try:
                update_fields["planned_end"] = datetime.fromisoformat(
                    parameters["due_date"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        if not update_fields:
            return {"success": False, "error": "没有提供要更新的字段"}

        for field, value in update_fields.items():
            setattr(task, field, value)

        task.updated_at = datetime.now()
        await db.commit()
        await db.refresh(task)

        return {
            "success": True,
            "message": f"任务 '{task.name}' 更新成功",
            "data": {
                "task_id": task.id,
                "name": task.name,
                "updated_fields": list(update_fields.keys()),
            }
        }

    async def _execute_assign_task(
        self,
        db: AsyncSession,
        user_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行分配任务"""
        task_id = parameters.get("task_id")
        task_name = parameters.get("task_name") or parameters.get("name")
        assignee_name = parameters.get("assignee_name")
        assignee_id = parameters.get("assignee_id")

        task = None
        if task_id:
            result = await db.execute(
                select(Task).where(Task.id == task_id, Task.is_deleted == False)
            )
            task = result.scalar_one_or_none()
        elif task_name:
            result = await db.execute(
                select(Task).where(Task.name.ilike(f"%{task_name}%"), Task.is_deleted == False)
            )
            task = result.scalar_one_or_none()

        if not task:
            return {"success": False, "error": "未找到指定任务"}

        if not assignee_id and assignee_name:
            user = await self._find_user_by_name(db, assignee_name)
            if user:
                assignee_id = user.id

        if not assignee_id:
            return {"success": False, "error": "未指定负责人"}

        task.assignee_id = assignee_id
        task.updated_at = datetime.now()
        await db.commit()
        await db.refresh(task)

        # 发送通知
        try:
            assigner_result = await db.execute(select(User).where(User.id == user_id))
            assigner = assigner_result.scalar_one_or_none()
            assigner_name = assigner.username or assigner.full_name or "系统" if assigner else "系统"

            await create_notification(
                db=db,
                user_id=assignee_id,
                type="task_assigned",
                title=f"任务分配: {task.name}",
                content=f"{assigner_name} 将任务 '{task.name}' 分配给您",
                related_type="task",
                related_id=task.id,
            )
        except Exception as e:
            logger.warning("任务分配通知创建失败（已忽略）: %s", e, exc_info=True)

        return {
            "success": True,
            "message": f"任务 '{task.name}' 已分配",
            "data": {
                "task_id": task.id,
                "name": task.name,
                "assignee_id": assignee_id,
            }
        }

    async def _execute_query_tasks(
        self,
        db: AsyncSession,
        user_id: str,
        project_id: Optional[str],
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行查询任务"""
        query = select(Task).where(Task.is_deleted == False)

        if project_id:
            query = query.where(Task.project_id == project_id)
        elif parameters.get("project_id"):
            query = query.where(Task.project_id == parameters.get("project_id"))

        if parameters.get("status"):
            query = query.where(Task.status == parameters.get("status"))
        if parameters.get("assignee_id"):
            query = query.where(Task.assignee_id == parameters.get("assignee_id"))
        if parameters.get("priority"):
            query = query.where(Task.priority == int(parameters.get("priority")))
        if parameters.get("search"):
            query = query.where(Task.name.ilike(f"%{parameters.get('search')}%"))

        query = query.order_by(Task.created_at.desc()).limit(50)
        result = await db.execute(query)
        tasks = result.scalars().all()

        task_list = []
        for task in tasks:
            task_list.append({
                "id": task.id,
                "name": task.name,
                "status": task.status,
                "priority": task.priority,
                "progress": float(task.progress) if task.progress else 0,
                "assignee_id": task.assignee_id,
                "planned_end": task.planned_end.isoformat() if task.planned_end else None,
                "project_id": task.project_id,
            })

        return {
            "success": True,
            "message": f"查询到 {len(task_list)} 个任务",
            "data": {
                "tasks": task_list,
                "total": len(task_list),
            }
        }

    async def _execute_create_project(
        self,
        db: AsyncSession,
        user_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行创建项目"""
        name = parameters.get("name") or parameters.get("project_name")
        if not name:
            return {"success": False, "error": "项目名称不能为空"}

        project = Project(
            name=name,
            description=parameters.get("description"),
            industry_type=parameters.get("industry_type", "it_software"),
            project_type=parameters.get("project_type", "agile"),
            priority=parameters.get("priority", 3),
            color=parameters.get("color", "#1890ff"),
            owner_id=user_id,
        )

        if parameters.get("start_date"):
            try:
                project.start_date = date.fromisoformat(parameters.get("start_date"))
            except (ValueError, AttributeError):
                pass
        if parameters.get("end_date"):
            try:
                project.end_date = date.fromisoformat(parameters.get("end_date"))
            except (ValueError, AttributeError):
                pass
        if parameters.get("budget"):
            try:
                project.budget = float(parameters.get("budget"))
            except (ValueError, TypeError):
                pass

        db.add(project)
        await db.commit()
        await db.refresh(project)

        return {
            "success": True,
            "message": f"项目 '{name}' 创建成功",
            "data": {
                "project_id": project.id,
                "name": project.name,
                "status": project.status,
                "owner_id": project.owner_id,
            }
        }

    async def _execute_add_comment(
        self,
        db: AsyncSession,
        user_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行添加评论"""
        task_id = parameters.get("task_id")
        content = parameters.get("content")

        if not task_id:
            return {"success": False, "error": "未指定任务ID"}
        if not content:
            return {"success": False, "error": "评论内容不能为空"}

        result = await db.execute(
            select(Task).where(Task.id == task_id, Task.is_deleted == False)
        )
        task = result.scalar_one_or_none()
        if not task:
            return {"success": False, "error": "任务不存在"}

        comment = Comment(
            content=content,
            task_id=task_id,
            project_id=task.project_id,
            user_id=user_id,
        )

        db.add(comment)
        await db.commit()
        await db.refresh(comment)

        return {
            "success": True,
            "message": "评论添加成功",
            "data": {
                "comment_id": comment.id,
                "task_id": task_id,
                "content": content,
            }
        }

    async def _execute_generate_report(
        self,
        db: AsyncSession,
        user_id: str,
        project_id: Optional[str],
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行生成报告"""
        target_project_id = parameters.get("project_id") or project_id
        report_type = parameters.get("report_type", "summary")

        if not target_project_id:
            return {"success": False, "error": "未指定项目ID"}

        result = await db.execute(
            select(Project).where(Project.id == target_project_id, Project.is_deleted == False)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"success": False, "error": "项目不存在"}

        # 统计任务
        task_stats_result = await db.execute(
            select(
                func.count(Task.id).label("total"),
                func.sum(case((Task.status == 'done', 1), else_=0)).label("completed"),
                func.avg(Task.progress).label("avg_progress"),
            ).where(Task.project_id == target_project_id, Task.is_deleted == False)
        )
        task_stats = task_stats_result.one()

        # 统计逾期任务
        overdue_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == target_project_id,
                Task.is_deleted == False,
                Task.planned_end < datetime.now(),
                Task.status != 'done'
            )
        )
        overdue_count = overdue_result.scalar()

        report_data = {
            "project_id": project.id,
            "project_name": project.name,
            "report_type": report_type,
            "generated_at": datetime.now().isoformat(),
            "task_summary": {
                "total": task_stats.total or 0,
                "completed": task_stats.completed or 0,
                "in_progress": (task_stats.total or 0) - (task_stats.completed or 0),
                "overdue": overdue_count or 0,
                "avg_progress": round(float(task_stats.avg_progress or 0), 2),
            },
            "project_status": project.status,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
        }

        return {
            "success": True,
            "message": f"报告生成成功: {project.name}",
            "data": report_data,
        }

    async def _execute_send_notification(
        self,
        db: AsyncSession,
        user_id: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行发送通知"""
        recipient_id = parameters.get("recipient_id")
        recipient_name = parameters.get("recipient_name")
        title = parameters.get("title")
        content = parameters.get("content")

        if not title:
            return {"success": False, "error": "通知标题不能为空"}

        if not recipient_id and recipient_name:
            user = await self._find_user_by_name(db, recipient_name)
            if user:
                recipient_id = user.id

        if not recipient_id:
            return {"success": False, "error": "未指定接收人"}

        notification = await create_notification(
            db=db,
            user_id=recipient_id,
            type="agent_notification",
            title=title,
            content=content,
            related_type="agent",
            related_id=user_id,
        )

        return {
            "success": True,
            "message": "通知发送成功",
            "data": {
                "notification_id": notification.id,
                "recipient_id": recipient_id,
                "title": title,
            }
        }

    async def _execute_schedule_meeting(
        self,
        db: AsyncSession,
        user_id: str,
        project_id: Optional[str],
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行安排会议（创建会议任务）"""
        name = parameters.get("name") or parameters.get("meeting_name") or "会议"
        target_project_id = parameters.get("project_id") or project_id

        if not target_project_id:
            return {"success": False, "error": "未指定项目ID"}

        # 验证项目存在
        project_result = await db.execute(
            select(Project).where(Project.id == target_project_id, Project.is_deleted == False)
        )
        project = project_result.scalar_one_or_none()
        if not project:
            return {"success": False, "error": "项目不存在"}

        # 计算WBS编码
        sibling_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.project_id == target_project_id,
                Task.parent_task_id == None,
                Task.is_deleted == False
            )
        )
        sibling_count = sibling_result.scalar() + 1
        wbs_code = str(sibling_count)

        # 处理会议时间
        planned_start = None
        planned_end = None
        if parameters.get("start_time"):
            try:
                planned_start = datetime.fromisoformat(parameters.get("start_time").replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        if parameters.get("end_time"):
            try:
                planned_end = datetime.fromisoformat(parameters.get("end_time").replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        if not planned_end and planned_start:
            planned_end = planned_start + timedelta(hours=1)

        # 处理参与人
        participants = parameters.get("participants", [])
        description = parameters.get("description") or parameters.get("agenda") or ""
        if participants:
            description += f"\n\n参与人: {', '.join(participants)}"

        task = Task(
            project_id=target_project_id,
            wbs_code=wbs_code,
            name=f"[会议] {name}",
            description=description.strip(),
            status=TaskStatus.TODO.value,
            priority=TaskPriority.MEDIUM.value,
            planned_start=planned_start,
            planned_end=planned_end,
            category="meeting",
        )

        db.add(task)
        await db.commit()
        await db.refresh(task)

        return {
            "success": True,
            "message": f"会议 '{name}' 已安排",
            "data": {
                "task_id": task.id,
                "name": task.name,
                "planned_start": task.planned_start.isoformat() if task.planned_start else None,
                "planned_end": task.planned_end.isoformat() if task.planned_end else None,
                "project_id": task.project_id,
            }
        }

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        project_id: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Agent对话流式响应"""
        system_msgs = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        if project_id:
            system_msgs.append({"role": "system", "content": f"当前项目ID：{project_id}"})

        all_messages = system_msgs + messages

        try:
            async for chunk in self.engine.stream_chat(
                messages=all_messages,
                provider=self.provider_name,
                temperature=0.7,
                max_tokens=2000
            ):
                yield chunk
        except Exception as e:
            yield f"Agent服务暂时不可用：{str(e)}"

    async def chat(
        self,
        messages: List[Dict[str, str]],
        project_id: Optional[str] = None,
    ) -> str:
        """Agent对话非流式响应"""
        system_msgs = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        if project_id:
            system_msgs.append({"role": "system", "content": f"当前项目ID：{project_id}"})

        all_messages = system_msgs + messages

        try:
            return await self.engine.chat(
                messages=all_messages,
                provider=self.provider_name,
                temperature=0.7,
                max_tokens=2000
            )
        except Exception as e:
            return f"Agent服务暂时不可用：{str(e)}"

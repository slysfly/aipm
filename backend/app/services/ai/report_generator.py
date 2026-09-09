"""[CPMAI Phase: CPMAI Phase: Model Evaluation | Domain: CPMAI Methodology — AI报告生成]"""
import json
import re
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case

from app.core.ai_engine import ai_engine
from app.models import Task, TaskStatus, Comment, Project, Risk, Milestone, User
from app.models.permission import ProjectMember


DAILY_REPORT_PROMPT = """你是一位专业的项目管理助手，请根据以下用户的当日工作数据，生成一份结构化的日报摘要。

用户工作数据（JSON格式）：
{work_data}

请严格按照以下JSON格式输出日报（不要包含任何markdown代码块标记，只输出纯JSON）：
{{
    "summary": "今日工作摘要，2-3句话概括今天的主要成果",
    "completed_tasks": [
        {{
            "task_id": "任务ID",
            "title": "任务标题",
            "project_name": "所属项目名称",
            "description": "完成情况的简要描述"
        }}
    ],
    "in_progress_tasks": [
        {{
            "task_id": "任务ID",
            "title": "任务标题",
            "project_name": "所属项目名称",
            "progress": 65,
            "description": "当前进展描述"
        }}
    ],
    "blockers": [
        {{
            "type": "task|resource|dependency|other",
            "description": "阻塞项描述",
            "related_task_id": "相关任务ID（如有）"
        }}
    ],
    "tomorrow_plan": [
        "明天计划完成的事项1",
        "明天计划完成的事项2"
    ],
    "stats": {{
        "completed_count": 0,
        "in_progress_count": 0,
        "comments_count": 0,
        "total_hours": 0
    }}
}}

要求：
1. summary 要简洁有力，突出今日关键成果
2. completed_tasks 和 in_progress_tasks 基于提供的数据如实填写
3. blockers 要从任务描述、评论中识别潜在的阻塞问题
4. tomorrow_plan 基于进行中的任务和项目进度合理推断
5. 所有数据必须基于提供的工作数据，不要编造
6. 只输出JSON，不要任何解释文字"""


WEEKLY_REPORT_PROMPT = """你是一位资深的项目管理专家，请根据以下用户本周的工作数据，生成一份结构化的周报。

用户本周工作数据（JSON格式）：
{work_data}

请严格按照以下JSON格式输出周报（不要包含任何markdown代码块标记，只输出纯JSON）：
{{
    "summary": "本周工作综述，3-5句话概括本周整体表现和关键成果",
    "highlights": [
        "本周亮点1：具体成果",
        "本周亮点2：具体成果",
        "本周亮点3：具体成果"
    ],
    "completed": [
        {{
            "task_id": "任务ID",
            "title": "任务标题",
            "project_name": "所属项目名称",
            "completed_at": "完成时间",
            "description": "完成情况描述"
        }}
    ],
    "in_progress": [
        {{
            "task_id": "任务ID",
            "title": "任务标题",
            "project_name": "所属项目名称",
            "progress": 65,
            "description": "当前进展"
        }}
    ],
    "blockers": [
        {{
            "type": "task|resource|dependency|other",
            "description": "阻塞项描述",
            "duration_days": 3,
            "related_task_id": ""
        }}
    ],
    "next_week_plan": [
        "下周计划1",
        "下周计划2",
        "下周计划3"
    ],
    "stats": {{
        "completed_tasks": 0,
        "total_hours": 0,
        "project_count": 0,
        "comment_count": 0,
        "avg_task_completion_time": 0
    }}
}}

要求：
1. summary 要全面概括本周工作，体现价值和进展
2. highlights 要突出本周最重要的3-5个成果
3. stats 中的数据要基于实际数据计算
4. next_week_plan 要基于未完成的工作和项目优先级合理安排
5. blockers 要识别本周遇到的和仍然存在的阻塞
6. 所有数据必须基于提供的工作数据，不要编造
7. 只输出JSON，不要任何解释文字"""


PROJECT_REPORT_PROMPT = """你是一位资深的项目管理和业务分析专家，请根据以下项目数据，生成一份项目状态报告。

项目数据（JSON格式）：
{project_data}

请严格按照以下JSON格式输出项目报告（不要包含任何markdown代码块标记，只输出纯JSON）：
{{
    "summary": "项目整体状态摘要，3-5句话概括项目健康状况、关键进展和风险",
    "health_score": 85,
    "health_status": "healthy|warning|critical",
    "progress": {{
        "total_tasks": 0,
        "completed_tasks": 0,
        "completion_rate": 0,
        "avg_progress": 0,
        "milestone_status": "on_track|at_risk|delayed"
    }},
    "risks": [
        {{
            "name": "风险名称",
            "level": "high|medium|low",
            "description": "风险描述",
            "impact": "对项目的影响描述"
        }}
    ],
    "team_contributions": [
        {{
            "user_id": "用户ID",
            "user_name": "用户姓名",
            "completed_tasks": 0,
            "total_hours": 0,
            "contribution_summary": "贡献描述"
        }}
    ],
    "milestones": [
        {{
            "name": "里程碑名称",
            "due_date": "截止日期",
            "status": "completed|on_track|at_risk|delayed",
            "description": "状态描述"
        }}
    ],
    "recommendations": [
        "建议1：基于项目数据的 actionable 建议",
        "建议2：基于项目数据的 actionable 建议",
        "建议3：基于项目数据的 actionable 建议"
    ],
    "stats": {{
        "total_tasks": 0,
        "completed_tasks": 0,
        "in_progress_tasks": 0,
        "total_risks": 0,
        "high_risks": 0,
        "team_size": 0,
        "total_hours": 0
    }}
}}

要求：
1. summary 要客观反映项目真实状态
2. health_score 是0-100的分数，基于进度、风险、里程碑综合评估
3. health_status 基于 health_score：>=80 healthy, >=60 warning, <60 critical
4. team_contributions 要体现每个成员的实际贡献
5. recommendations 要具体、可执行
6. 所有数据必须基于提供的项目数据，不要编造
7. 只输出JSON，不要任何解释文字"""


class ReportGenerator:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.engine = ai_engine

    def _extract_json(self, text: str) -> Dict[str, Any]:
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

        return json.loads(text)

    def _safe_json_loads(self, text: str, default: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._extract_json(text)
        except (json.JSONDecodeError, ValueError):
            return default

    async def _get_user_tasks_for_date(
        self,
        user_id: str,
        target_date: date
    ) -> Dict[str, Any]:
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = datetime.combine(target_date + timedelta(days=1), datetime.min.time())

        result = await self.db.execute(
            select(Task, Project.name.label("project_name"))
            .join(Project, Task.project_id == Project.id)
            .where(
                and_(
                    Task.assignee_id == user_id,
                    Task.is_deleted == False,
                    or_(
                        and_(Task.actual_end >= start_dt, Task.actual_end < end_dt),
                        and_(Task.updated_at >= start_dt, Task.updated_at < end_dt),
                        Task.status == TaskStatus.IN_PROGRESS.value,
                    )
                )
            )
        )
        tasks = result.fetchall()

        completed = []
        in_progress = []
        for task_row in tasks:
            task = task_row[0]
            project_name = task_row[1]
            task_data = {
                "task_id": task.id,
                "title": task.name,
                "project_name": project_name,
                "description": task.description or "",
                "status": task.status,
                "progress": float(task.progress or 0),
            }
            if task.status == TaskStatus.DONE.value and task.actual_end and start_dt <= task.actual_end < end_dt:
                completed.append(task_data)
            elif task.status == TaskStatus.IN_PROGRESS.value:
                in_progress.append(task_data)

        result = await self.db.execute(
            select(func.sum(Task.actual_hours))
            .where(
                and_(
                    Task.assignee_id == user_id,
                    Task.is_deleted == False,
                    Task.updated_at >= start_dt,
                    Task.updated_at < end_dt,
                )
            )
        )
        total_hours = result.scalar() or 0

        return {
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "total_hours": float(total_hours) if total_hours else 0,
        }

    async def _get_user_comments_for_date(
        self,
        user_id: str,
        target_date: date
    ) -> List[Dict[str, Any]]:
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = datetime.combine(target_date + timedelta(days=1), datetime.min.time())

        result = await self.db.execute(
            select(Comment, Task.name.label("task_name"), Project.name.label("project_name"))
            .join(Task, Comment.task_id == Task.id)
            .join(Project, Task.project_id == Project.id)
            .where(
                and_(
                    Comment.user_id == user_id,
                    Comment.is_deleted == False,
                    Comment.created_at >= start_dt,
                    Comment.created_at < end_dt,
                )
            )
        )
        comments = result.fetchall()

        return [
            {
                "comment_id": c[0].id,
                "content": c[0].content,
                "task_name": c[1],
                "project_name": c[2],
                "created_at": c[0].created_at.isoformat() if c[0].created_at else None,
            }
            for c in comments
        ]

    async def _get_user_tasks_for_period(
        self,
        user_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())

        result = await self.db.execute(
            select(Task, Project.name.label("project_name"))
            .join(Project, Task.project_id == Project.id)
            .where(
                and_(
                    Task.assignee_id == user_id,
                    Task.is_deleted == False,
                    or_(
                        and_(Task.actual_end >= start_dt, Task.actual_end < end_dt),
                        and_(Task.updated_at >= start_dt, Task.updated_at < end_dt),
                        Task.status == TaskStatus.IN_PROGRESS.value,
                    )
                )
            )
        )
        tasks = result.fetchall()

        completed = []
        in_progress = []
        for task_row in tasks:
            task = task_row[0]
            project_name = task_row[1]
            task_data = {
                "task_id": task.id,
                "title": task.name,
                "project_name": project_name,
                "description": task.description or "",
                "status": task.status,
                "progress": float(task.progress or 0),
                "actual_hours": float(task.actual_hours or 0),
                "completed_at": task.actual_end.isoformat() if task.actual_end else None,
            }
            if task.status == TaskStatus.DONE.value and task.actual_end and start_dt <= task.actual_end < end_dt:
                completed.append(task_data)
            elif task.status == TaskStatus.IN_PROGRESS.value:
                in_progress.append(task_data)

        result = await self.db.execute(
            select(func.sum(Task.actual_hours))
            .where(
                and_(
                    Task.assignee_id == user_id,
                    Task.is_deleted == False,
                    Task.updated_at >= start_dt,
                    Task.updated_at < end_dt,
                )
            )
        )
        total_hours = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(Comment.id))
            .where(
                and_(
                    Comment.user_id == user_id,
                    Comment.is_deleted == False,
                    Comment.created_at >= start_dt,
                    Comment.created_at < end_dt,
                )
            )
        )
        comment_count = result.scalar() or 0

        project_ids = list(set(t[0].project_id for t in tasks))

        return {
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "total_hours": float(total_hours) if total_hours else 0,
            "comment_count": comment_count,
            "project_count": len(project_ids),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }

    async def _get_project_data(
        self,
        project_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return {"error": "项目不存在"}

        if not start_date:
            start_date = project.start_date or date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        result = await self.db.execute(
            select(
                func.count(Task.id).label("total"),
                func.sum(case((Task.status == TaskStatus.DONE.value, 1), else_=0)).label("completed"),
                func.sum(case((Task.status == TaskStatus.IN_PROGRESS.value, 1), else_=0)).label("in_progress"),
                func.avg(Task.progress).label("avg_progress"),
                func.sum(Task.actual_hours).label("total_hours"),
            )
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False,
                )
            )
        )
        task_stats = result.fetchone()

        result = await self.db.execute(
            select(Risk)
            .where(Risk.project_id == project_id)
        )
        risks = result.scalars().all()

        result = await self.db.execute(
            select(Milestone)
            .where(Milestone.project_id == project_id)
        )
        milestones = result.scalars().all()

        result = await self.db.execute(
            select(
                Task.assignee_id,
                User.username,
                func.count(Task.id).label("completed_count"),
                func.sum(Task.actual_hours).label("total_hours"),
            )
            .join(User, Task.assignee_id == User.id, isouter=True)
            .where(
                and_(
                    Task.project_id == project_id,
                    Task.is_deleted == False,
                    Task.assignee_id.isnot(None),
                )
            )
            .group_by(Task.assignee_id, User.username)
        )
        member_stats = result.fetchall()

        result = await self.db.execute(
            select(ProjectMember, User)
            .join(User, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
        )
        members = result.fetchall()

        total_tasks = task_stats.total or 0
        completed_tasks = task_stats.completed or 0
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        return {
            "project_id": project.id,
            "project_name": project.name,
            "project_description": project.description or "",
            "project_status": project.status,
            "start_date": project.start_date.isoformat() if project.start_date else None,
            "end_date": project.end_date.isoformat() if project.end_date else None,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "task_stats": {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "in_progress_tasks": task_stats.in_progress or 0,
                "completion_rate": round(completion_rate, 2),
                "avg_progress": round(float(task_stats.avg_progress or 0), 2),
                "total_hours": float(task_stats.total_hours or 0),
            },
            "risks": [
                {
                    "risk_id": r.id,
                    "name": r.name,
                    "category": r.category,
                    "probability": float(r.probability or 0),
                    "impact": float(r.impact or 0),
                    "risk_score": float(r.risk_score or 0),
                    "status": r.status,
                    "description": r.description or "",
                }
                for r in risks
            ],
            "milestones": [
                {
                    "milestone_id": m.id,
                    "name": m.name,
                    "due_date": m.due_date.isoformat() if m.due_date else None,
                    "status": m.status,
                    "description": m.description or "",
                }
                for m in milestones
            ],
            "team_contributions": [
                {
                    "user_id": m[0].assignee_id,
                    "user_name": m[1] or "未知用户",
                    "completed_tasks": m[2] or 0,
                    "total_hours": float(m[3] or 0),
                }
                for m in member_stats
            ],
            "team_size": len(members),
        }

    async def generate_daily_report(
        self,
        user_id: str,
        target_date: date
    ) -> Dict[str, Any]:
        task_data = await self._get_user_tasks_for_date(user_id, target_date)
        comments = await self._get_user_comments_for_date(user_id, target_date)

        work_data = {
            "date": target_date.isoformat(),
            "user_id": user_id,
            "completed_tasks": task_data["completed_tasks"],
            "in_progress_tasks": task_data["in_progress_tasks"],
            "comments": comments,
            "total_hours": task_data["total_hours"],
        }

        prompt = DAILY_REPORT_PROMPT.format(work_data=json.dumps(work_data, ensure_ascii=False, indent=2))

        try:
            response = await self.engine.chat(
                [
                    {"role": "system", "content": "你是一个专业的项目管理日报生成助手。请严格按JSON格式输出。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=3000
            )
            ai_result = self._safe_json_loads(response, {})
        except Exception:
            ai_result = {}

        completed_count = len(task_data["completed_tasks"])
        in_progress_count = len(task_data["in_progress_tasks"])
        comments_count = len(comments)
        total_hours = task_data["total_hours"]

        default_summary = f"今日完成 {completed_count} 项任务，{in_progress_count} 项任务进行中。"
        if completed_count == 0 and in_progress_count == 0:
            default_summary = f"今日暂无任务更新，共发表 {comments_count} 条评论。"

        return {
            "report_type": "daily",
            "date": target_date.isoformat(),
            "user_id": user_id,
            "generated_at": datetime.now().isoformat(),
            "summary": ai_result.get("summary", default_summary),
            "completed_tasks": ai_result.get("completed_tasks", [
                {
                    "task_id": t["task_id"],
                    "title": t["title"],
                    "project_name": t["project_name"],
                    "description": t.get("description", ""),
                }
                for t in task_data["completed_tasks"]
            ]),
            "in_progress_tasks": ai_result.get("in_progress_tasks", [
                {
                    "task_id": t["task_id"],
                    "title": t["title"],
                    "project_name": t["project_name"],
                    "progress": t.get("progress", 0),
                    "description": t.get("description", ""),
                }
                for t in task_data["in_progress_tasks"]
            ]),
            "blockers": ai_result.get("blockers", []),
            "tomorrow_plan": ai_result.get("tomorrow_plan", []),
            "stats": {
                "completed_count": completed_count,
                "in_progress_count": in_progress_count,
                "comments_count": comments_count,
                "total_hours": round(total_hours, 2),
            },
            "raw_data": work_data,
        }

    async def generate_weekly_report(
        self,
        user_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        task_data = await self._get_user_tasks_for_period(user_id, start_date, end_date)

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())

        result = await self.db.execute(
            select(Comment, Task.name.label("task_name"), Project.name.label("project_name"))
            .join(Task, Comment.task_id == Task.id)
            .join(Project, Task.project_id == Project.id)
            .where(
                and_(
                    Comment.user_id == user_id,
                    Comment.is_deleted == False,
                    Comment.created_at >= start_dt,
                    Comment.created_at < end_dt,
                )
            )
        )
        comments = result.fetchall()

        work_data = {
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "user_id": user_id,
            "completed_tasks": task_data["completed_tasks"],
            "in_progress_tasks": task_data["in_progress_tasks"],
            "comments": [
                {
                    "comment_id": c[0].id,
                    "content": c[0].content,
                    "task_name": c[1],
                    "project_name": c[2],
                }
                for c in comments
            ],
            "total_hours": task_data["total_hours"],
            "comment_count": task_data["comment_count"],
            "project_count": task_data["project_count"],
        }

        prompt = WEEKLY_REPORT_PROMPT.format(work_data=json.dumps(work_data, ensure_ascii=False, indent=2))

        try:
            response = await self.engine.chat(
                [
                    {"role": "system", "content": "你是一个专业的项目管理周报生成助手。请严格按JSON格式输出。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=4000
            )
            ai_result = self._safe_json_loads(response, {})
        except Exception:
            ai_result = {}

        completed_count = len(task_data["completed_tasks"])
        in_progress_count = len(task_data["in_progress_tasks"])
        total_hours = task_data["total_hours"]
        project_count = task_data["project_count"]
        comment_count = task_data["comment_count"]

        default_summary = f"本周完成 {completed_count} 项任务，涉及 {project_count} 个项目，累计投入 {round(total_hours, 1)} 工时。"
        if completed_count == 0:
            default_summary = f"本周暂无完成任务，{in_progress_count} 项任务进行中，累计投入 {round(total_hours, 1)} 工时。"

        return {
            "report_type": "weekly",
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "user_id": user_id,
            "generated_at": datetime.now().isoformat(),
            "summary": ai_result.get("summary", default_summary),
            "highlights": ai_result.get("highlights", [
                f"完成 {completed_count} 项任务" if completed_count > 0 else None,
                f"参与 {project_count} 个项目的工作" if project_count > 1 else None,
                f"累计投入 {round(total_hours, 1)} 工时" if total_hours > 0 else None,
            ]),
            "completed": ai_result.get("completed", [
                {
                    "task_id": t["task_id"],
                    "title": t["title"],
                    "project_name": t["project_name"],
                    "completed_at": t.get("completed_at"),
                    "description": t.get("description", ""),
                }
                for t in task_data["completed_tasks"]
            ]),
            "in_progress": ai_result.get("in_progress", [
                {
                    "task_id": t["task_id"],
                    "title": t["title"],
                    "project_name": t["project_name"],
                    "progress": t.get("progress", 0),
                    "description": t.get("description", ""),
                }
                for t in task_data["in_progress_tasks"]
            ]),
            "blockers": ai_result.get("blockers", []),
            "next_week_plan": ai_result.get("next_week_plan", []),
            "stats": {
                "completed_tasks": completed_count,
                "total_hours": round(total_hours, 2),
                "project_count": project_count,
                "comment_count": comment_count,
                "avg_task_completion_time": round(total_hours / max(completed_count, 1), 2),
            },
            "raw_data": work_data,
        }

    async def generate_project_report(
        self,
        project_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        project_data = await self._get_project_data(project_id, start_date, end_date)

        if "error" in project_data:
            return project_data

        prompt = PROJECT_REPORT_PROMPT.format(
            project_data=json.dumps(project_data, ensure_ascii=False, indent=2)
        )

        try:
            response = await self.engine.chat(
                [
                    {"role": "system", "content": "你是一个专业的项目状态报告生成助手。请严格按JSON格式输出。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            ai_result = self._safe_json_loads(response, {})
        except Exception:
            ai_result = {}

        task_stats = project_data["task_stats"]
        total_risks = len(project_data["risks"])
        high_risks = len([r for r in project_data["risks"] if (r.get("risk_score") or 0) > 0.5])

        completion_rate = task_stats["completion_rate"]
        avg_progress = task_stats["avg_progress"]

        if completion_rate >= 80 and high_risks == 0:
            default_health = "healthy"
            default_score = 85
        elif completion_rate >= 60:
            default_health = "warning"
            default_score = 70
        else:
            default_health = "critical"
            default_score = 50

        default_summary = (
            f"项目「{project_data['project_name']}」当前完成率 {completion_rate}%，"
            f"平均进度 {avg_progress}%。共有 {total_risks} 个风险，其中 {high_risks} 个高风险。"
        )

        return {
            "report_type": "project",
            "project_id": project_id,
            "project_name": project_data["project_name"],
            "period_start": project_data.get("period_start"),
            "period_end": project_data.get("period_end"),
            "generated_at": datetime.now().isoformat(),
            "summary": ai_result.get("summary", default_summary),
            "health_score": ai_result.get("health_score", default_score),
            "health_status": ai_result.get("health_status", default_health),
            "progress": ai_result.get("progress", {
                "total_tasks": task_stats["total_tasks"],
                "completed_tasks": task_stats["completed_tasks"],
                "completion_rate": completion_rate,
                "avg_progress": avg_progress,
                "milestone_status": "on_track",
            }),
            "risks": ai_result.get("risks", [
                {
                    "name": r["name"],
                    "level": "high" if (r.get("risk_score") or 0) > 0.5 else "medium" if (r.get("risk_score") or 0) > 0.3 else "low",
                    "description": r.get("description", ""),
                    "impact": f"风险评分: {r.get('risk_score', 0)}",
                }
                for r in project_data["risks"][:5]
            ]),
            "team_contributions": ai_result.get("team_contributions", project_data["team_contributions"]),
            "milestones": ai_result.get("milestones", [
                {
                    "name": m["name"],
                    "due_date": m["due_date"],
                    "status": m["status"],
                    "description": m.get("description", ""),
                }
                for m in project_data["milestones"]
            ]),
            "recommendations": ai_result.get("recommendations", [
                "关注高风险项的应对措施",
                "定期跟踪里程碑进度",
                "优化资源分配以提高效率",
            ]),
            "stats": {
                "total_tasks": task_stats["total_tasks"],
                "completed_tasks": task_stats["completed_tasks"],
                "in_progress_tasks": task_stats["in_progress_tasks"],
                "total_risks": total_risks,
                "high_risks": high_risks,
                "team_size": project_data["team_size"],
                "total_hours": task_stats["total_hours"],
            },
            "raw_data": project_data,
        }

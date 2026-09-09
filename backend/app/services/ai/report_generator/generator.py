"""ReportGenerator 门面类 —— 组合 collectors 和 templates，提供报告生成能力"""

import json
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.ai_engine import ai_engine
from app.models import Comment, Task, Project

from .formatters import safe_json_loads
from .collectors.task_collector import TaskCollector
from .collectors.comment_collector import CommentCollector
from .collectors.project_collector import ProjectCollector
from .templates.daily import DAILY_REPORT_PROMPT
from .templates.weekly import WEEKLY_REPORT_PROMPT
from .templates.project import PROJECT_REPORT_PROMPT


class ReportGenerator:
    """AI 报告生成器 —— 生成日报、周报、项目报告"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.engine = ai_engine
        self._task_collector = TaskCollector(db)
        self._comment_collector = CommentCollector(db)
        self._project_collector = ProjectCollector(db)

    # ─── 公开方法 ───────────────────────────────────────────────

    async def generate_daily_report(
        self,
        user_id: str,
        target_date: date
    ) -> Dict[str, Any]:
        task_data = await self._task_collector.get_user_tasks_for_date(user_id, target_date)
        comments = await self._comment_collector.get_user_comments_for_date(user_id, target_date)

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
            ai_result = safe_json_loads(response, {})
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
        task_data = await self._task_collector.get_user_tasks_for_period(user_id, start_date, end_date)

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
            ai_result = safe_json_loads(response, {})
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
        project_data = await self._project_collector.get_project_data(project_id, start_date, end_date)

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
            ai_result = safe_json_loads(response, {})
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

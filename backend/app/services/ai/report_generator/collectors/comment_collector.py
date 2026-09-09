"""评论收集"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models import Comment, Task, Project


class CommentCollector:
    """收集用户评论数据的收集器"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_comments_for_date(
        self,
        user_id: str,
        target_date: date
    ) -> List[Dict[str, Any]]:
        """获取用户在指定日期的评论数据"""
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

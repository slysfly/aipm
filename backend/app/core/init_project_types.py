"""
PMI中国AI项目管理社区 — 默认项目类型种子

在系统启动时确保存在基础项目类型（agile/waterfall/hybrid/kanban），
使历史项目的 project_type 取值（code）能解析到对应标签与颜色。
这是结构性默认，非演示数据，故不受 enable_seed_data 开关控制，始终确保。
"""

import logging

from sqlalchemy import select, func
from app.db.session import async_session_maker
from app.models import ProjectType

logger = logging.getLogger("app.init_project_types")

# (code, name, color, sort_order)
DEFAULT_TYPES = [
    ("agile", "敏捷", "#1890ff", 0),
    ("waterfall", "瀑布", "#13C2C2", 1),
    ("hybrid", "混合", "#722ED1", 2),
    ("kanban", "看板", "#52C41A", 3),
]


async def ensure_default_project_types() -> None:
    """若 project_types 表为空，则写入默认类型。已存在则跳过（不覆盖用户自定义）。"""
    try:
        async with async_session_maker() as db:
            cnt = (await db.execute(select(func.count(ProjectType.id)))).scalar() or 0
            if cnt > 0:
                return
            for code, name, color, order in DEFAULT_TYPES:
                db.add(
                    ProjectType(
                        name=name,
                        code=code,
                        color=color,
                        description=f"系统默认类型：{name}",
                        is_system=True,
                        sort_order=order,
                    )
                )
            await db.commit()
            logger.info("已写入默认项目类型 %d 个", len(DEFAULT_TYPES))
    except Exception as e:
        logger.warning("默认项目类型种子失败（已忽略）: %s", e)

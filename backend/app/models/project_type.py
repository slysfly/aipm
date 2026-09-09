from sqlalchemy import text
"""
PMI中国AI项目管理社区 — 可自定义项目类型模型

用于替代原先写死的 ProjectType 枚举（agile/waterfall/hybrid/kanban）。
项目类型由用户在同一套全局列表中自定义（名称 + 颜色 + 描述 + 排序），
所有项目创建/编辑时从中选择，并在项目列表、组合、看板等各板块统一显示与筛选。

Project.project_type 列存放本表的 code（稳定标识），标签/颜色从本表解析。
"""

from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, func
from app.db.session import Base
from app.models import generate_uuid


class ProjectType(Base):
    """可自定义项目类型"""

    __tablename__ = "project_types"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False, index=True)
    # 稳定标识，存于 Project.project_type；创建后不可更改，保证已有项目引用不失效
    code = Column(String(50), nullable=False, unique=True, index=True)
    color = Column(String(7), default="#1890ff")  # Hex 颜色
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, default=False)  # 系统内置默认类型
    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))
    updated_at = Column(DateTime(timezone=True), server_default=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"), onupdate=text("(strftime(%Y-%m-%d %H:%M:%S, now, localtime))"))

    def __repr__(self):
        return f"<ProjectType {self.code}:{self.name}>"

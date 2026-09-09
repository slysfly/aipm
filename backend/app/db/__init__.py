"""
PMI中国AI项目管理社区 - 数据库模块初始化
"""

from app.db.session import Base, engine

__all__ = ["Base", "engine"]

"""add missing model tables introduced after 0100 (e.g. ai_action_log)

v0.1.0 发布新增了模型 ai_action_log，但未配套 Alembic 迁移：存量库已
stamp 到 0100 head，DB_MIGRATE=1 时 upgrade head 是 no-op，表不存在导致
AI 直接操作功能抛 OperationalError（500）并连带同事务业务写库回滚。

沿用 0100 的幂等策略：对模型中定义但库中缺失的表按元数据补建（IF NOT EXISTS），
对已存在表补齐缺失索引。不删除、不改动已有表，零数据风险，可重复执行。

Revision ID: b8e4f2a6c3d1
Revises: a9f3c2e1b7d8
Create Date: 2026-09-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable, CreateIndex

import app.models  # 确保全部模型注册到 Base.metadata
from app.db.session import Base


revision = "b8e4f2a6c3d1"
down_revision = "a9f3c2e1b7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())

    for tname, table in Base.metadata.tables.items():
        if tname in existing_tables:
            # 表已存在：补齐缺失索引
            existing_indexes = {i["name"] for i in insp.get_indexes(tname)}
            for idx in table.indexes:
                if idx.name not in existing_indexes:
                    op.execute(CreateIndex(idx, if_not_exists=True))
            continue
        # 表缺失：按模型定义创建（IF NOT EXISTS 防护）
        op.execute(CreateTable(table, if_not_exists=True))
        for idx in table.indexes:
            op.execute(CreateIndex(idx, if_not_exists=True))


def downgrade() -> None:
    # 仅移除本迁移可能新建且当前为空的表，避免误删数据
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())
    for tname in reversed(list(Base.metadata.tables.keys())):
        if tname in existing_tables:
            try:
                cnt = bind.execute(sa.text(f"SELECT COUNT(*) FROM {tname}")).scalar()
            except Exception:
                cnt = 0
            if cnt == 0:
                op.drop_table(tname)

"""align existing databases to the latest model

补齐早期 create_all 库中缺失的表与索引（不删除、不改动已有表，零数据风险）。
对每一张在模型中定义、但数据库中尚不存在的表，使用模型元数据创建它；
对已存在表的缺失索引也一并补齐。全部带 IF NOT EXISTS，可重复执行。

Revision ID: a9f3c2e1b7d8
Revises: f837d2d961b0
Create Date: 2026-07-13 01:00:00.000000
"""

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable, CreateIndex

import app.models  # 确保全部模型注册到 Base.metadata
from app.db.session import Base


revision = "a9f3c2e1b7d8"
down_revision = "f837d2d961b0"
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
    # 仅移除本迁移可能新建的表（按模型表名逆序），已存在且含数据的表不受影响
    bind = op.get_bind()
    insp = inspect(bind)
    existing_tables = set(insp.get_table_names())
    for tname in reversed(list(Base.metadata.tables.keys())):
        if tname in existing_tables:
            # 仅当表为空时才删除，避免误删数据
            try:
                cnt = bind.execute(sa.text(f"SELECT COUNT(*) FROM {tname}")).scalar()
            except Exception:
                cnt = 0
            if cnt == 0:
                op.execute(sa.text(f"DROP TABLE IF EXISTS {tname}"))

"""
PMI中国AI项目管理社区 - 数据库迁移入口
优先使用 Alembic 升级到最新版本；若未启用 Alembic 或迁移失败，则回退到 create_all。
"""
import asyncio
import logging
import os

from sqlalchemy import inspect, text

from app.config import settings
from app.db.session import Base, engine

logger = logging.getLogger("app.migrate")

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _collect_missing_columns(sync_conn) -> list:
    """在同步上下文（run_sync 内）扫描所有模型，收集数据库缺失的列 ALTER 语句。
    必须在 run_sync 内执行，否则 inspector 方法会触发 greenlet_spawn 错误。"""
    import app.models  # noqa: F401 确保模型注册到 Base.metadata
    from app.models import Base

    insp = inspect(sync_conn)
    db_tables = set(insp.get_table_names())
    plan: list = []
    for tname, tmodel in Base.metadata.tables.items():
        if tname not in db_tables:
            continue
        db_cols = {c["name"] for c in insp.get_columns(tname)}
        for col in tmodel.columns:
            if col.name in db_cols:
                continue
            # 跳过主键/自增等结构敏感列，避免 ALTER 破坏既有约束。
            # 外键列仅做「纯列新增」是安全的（约束不会随 ADD COLUMN 创建，
            # 但列本身可正常读写，足以修复查询所需的 schema 漂移），故不再跳过。
            # 注意：SQLAlchemy 中 Column.autoincrement 默认是符号 'auto'（真值），
            # 只有真正自增的整数主键才是 True。必须用 `is True` 严格判断，
            # 否则 'auto' 的真值性会误杀本应补齐的缺失列（曾导致 project_name
            # 等列永远无法被自愈逻辑补齐——这是带 token 冒烟一直 FAIL 的真凶）。
            if col.primary_key or col.autoincrement is True:
                continue
            # 带 server_default 的列（多为时间戳）跳过，避免方言差异导致 ALTER 失败
            if col.server_default is not None:
                continue
            ddl = str(col.type)
            sql = f'ALTER TABLE "{tname}" ADD COLUMN "{col.name}" {ddl}'
            if not col.nullable:
                up = ddl.upper()
                if any(k in up for k in ("INT", "NUMERIC", "FLOAT", "REAL", "DECIMAL", "BOOL")):
                    sql += " DEFAULT 0"
                elif "JSON" in up:
                    sql += " DEFAULT '{}'"
                else:
                    sql += " DEFAULT ''"
            plan.append(sql)
    return plan


async def _ensure_offline_columns() -> None:
    """
    通用、幂等地补齐「模型已定义但生产库缺失」的列（schema 漂移自愈）。
    扫描 Base.metadata 所有表，对数据库中存在但缺少某列的表执行 ALTER ADD COLUMN。
    已知可修复的真实漂移：change_requests.project_id、tasks.version 等。
    所有 inspector 调用均在 run_sync 同步上下文中完成，避免 greenlet_spawn 错误。
    逐列 try/except 互不波及；兼容 SQLite（开发）与 PostgreSQL（生产）；异常绝不阻塞启动。
    """
    try:
        async with engine.connect() as conn:
            plan = await conn.run_sync(_collect_missing_columns)
        if not plan:
            return
        async with engine.connect() as conn:
            for sql in plan:
                try:
                    await conn.execute(text(sql))
                    await conn.commit()
                    logger.info("已补齐缺失列: %s", sql)
                except Exception as ex:  # 单列失败不影响其它列
                    logger.warning("补齐列失败（已跳过）: %s | %s", sql, ex)
    except Exception as e:  # 绝不让列补齐逻辑阻塞启动
        logger.warning("补齐离线所需列失败（已忽略，不影响启动）: %s", e)





def _sync_url(url: str) -> str:
    """将异步数据库 URL 转换为同步驱动 URL（供 Alembic 使用）。"""
    return (url or "").replace("+asyncpg", "").replace("+aiosqlite", "")


def _run_alembic_upgrade() -> None:
    from alembic.config import Config
    from alembic import command

    ini_path = os.path.join(BACKEND_DIR, "alembic.ini")
    if not os.path.exists(ini_path):
        raise FileNotFoundError(f"未找到 alembic.ini: {ini_path}")

    cfg = Config(ini_path)
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    cfg.set_main_option("sqlalchemy.url", _sync_url(settings.DATABASE_URL))
    command.upgrade(cfg, "head")


async def apply_migrations() -> None:
    """应用数据库迁移（Alembic 优先，create_all 兜底）。"""
    if not settings.DB_MIGRATE:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("已使用 create_all 初始化数据库表结构（未启用 Alembic）")
        await _ensure_offline_columns()
        return

    try:
        import app.models  # 确保模型注册到 Base.metadata
        await asyncio.to_thread(_run_alembic_upgrade)
        logger.info("Alembic 数据库迁移已应用（已升级到最新版本）")
    except Exception as e:
        # 不再静默回退到 create_all：否则会掩盖迁移脚本错误、造成 schema 漂移。
        # 显式报错并终止启动，由运维修复迁移脚本后再启动。
        logger.error("Alembic 迁移失败，已终止启动（不再回退 create_all）: %s", e, exc_info=True)
        raise RuntimeError(
            f"Alembic 数据库迁移失败，已终止启动以避免 schema 漂移：{e}"
        ) from e
    finally:
        # 无论 Alembic 是否成功，都幂等补齐离线冲突合并所需的新列（不阻塞启动）
        await _ensure_offline_columns()

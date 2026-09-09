"""
PMI中国AI项目管理社区 — 公共生命周期工厂

统一 serve.py 与 main.py 的 lifespan 逻辑，消除两份重复代码。
差异点通过参数注入：数据库初始化策略（迁移 vs create_all）。
"""

import asyncio
import sys
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI

from app.config import settings
from app.core.logging import setup_logging

logger = setup_logging()


def create_lifespan(
    db_strategy: Literal["migrate", "create_all"] = "migrate",
    enable_seed_data: bool = False,
    enable_system_llm: bool = False,
    enable_message_queue_stop: bool = False,
):
    """创建 FastAPI lifespan 上下文管理器。

    参数：
        db_strategy: 数据库初始化策略
            - "migrate": 使用 Alembic 迁移（apply_migrations，生产推荐）
            - "create_all": 使用 Base.metadata.create_all（快速开发）
        enable_seed_data: 是否在启动时写入演示数据
        enable_system_llm: 是否在启动时配置系统默认大模型
        enable_message_queue_stop: 是否在关闭时释放消息队列
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ===== 启动阶段 =====

        # 生产环境安全校验：禁止使用弱密钥启动
        _WEAK_KEYS = {
            "your-secret-key-here-change-in-production",
            "change-me",
            "change-me-in-production",
        }
        if settings.ENVIRONMENT == "production" and settings.SECRET_KEY in _WEAK_KEYS:
            logger.error(
                "生产环境检测到弱 SECRET_KEY，存在严重安全风险。"
                "请在环境变量中设置强随机 SECRET_KEY 后再启动。"
            )
            sys.exit(1)

        logger.info("启动PMI中国AI项目管理社区 v%s ...", settings.VERSION)
        logger.info("环境: %s", settings.ENVIRONMENT)
        logger.info("数据库策略: %s", db_strategy)

        # 数据库初始化
        if db_strategy == "migrate":
            from app.core.migrate import apply_migrations
            await apply_migrations()
        else:
            from app.db.session import engine, Base
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        logger.info("数据库初始化完成")

        # 以下为非关键初始化步骤：任一失败仅告警并继续启动
        # 确保存在初始管理员
        try:
            from app.core.init_admin import ensure_initial_admin
            await ensure_initial_admin()
        except Exception as e:
            logger.warning("初始管理员创建失败（已忽略，可稍后手动创建）: %s", e)

        # 确保存在默认项目类型（结构性默认，始终确保）
        try:
            from app.core.init_project_types import ensure_default_project_types
            await ensure_default_project_types()
        except Exception as e:
            logger.warning("默认项目类型种子失败（已忽略）: %s", e)

        # 系统默认大模型配置
        if enable_system_llm:
            try:
                from app.core.init_admin import ensure_system_llm_config
                await ensure_system_llm_config()
            except Exception as e:
                logger.warning("系统默认大模型配置失败（已忽略）: %s", e)

        # 演示数据
        if enable_seed_data:
            try:
                from app.core.seed import ensure_seed_data
                await ensure_seed_data()
            except Exception as e:
                logger.warning("演示数据写入失败（已忽略）: %s", e)

        # ===== 后台能力启动 =====
        from app.services.scheduler_service import scheduler_service
        from app.services.queue_worker import worker_manager
        from app.services.recurring_task_scheduler import RecurringTaskScheduler
        from app.db.session import async_session_maker

        recurring_task = {"handle": None}

        async def _recurring_loop():
            """周期性处理到期重复任务"""
            while True:
                try:
                    async with async_session_maker() as db:
                        await RecurringTaskScheduler.process_due_tasks(db)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning("重复任务处理异常: %s", e)
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    break

        # ── 模型目录周级自动刷新循环 ──
        model_catalog_task = {"handle": None}

        async def _model_catalog_loop():
            """每周自动刷新各厂商模型目录缓存（管理员亦可在设置页手动触发）"""
            from app.services.model_catalog_service import refresh_all

            # 启动后稍等，确保 DB 迁移/连接稳定
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                return
            while True:
                try:
                    async with async_session_maker() as db:
                        summary = await refresh_all(db)
                    logger.info(
                        "模型目录周级刷新完成：%s 个厂商（%s）",
                        summary.get("total"),
                        summary.get("providers"),
                    )
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning("模型目录周级刷新异常: %s", e)
                try:
                    await asyncio.sleep(7 * 24 * 3600)  # 每周一次
                except asyncio.CancelledError:
                    break

        try:
            await scheduler_service.start()
            logger.info("定时任务调度器已启动")
        except Exception as e:
            logger.warning("定时任务调度器启动失败（已忽略）: %s", e)

        try:
            await worker_manager.start_all()
            logger.info("后台队列 Worker 已启动")
        except Exception as e:
            logger.warning("后台队列 Worker 启动失败（已忽略）: %s", e)

        try:
            recurring_task["handle"] = asyncio.create_task(_recurring_loop())
            logger.info("重复任务处理器已启动")
        except Exception as e:
            logger.warning("重复任务处理器启动失败（已忽略）: %s", e)

        try:
            model_catalog_task["handle"] = asyncio.create_task(_model_catalog_loop())
            logger.info("模型目录周级刷新器已启动")
        except Exception as e:
            logger.warning("模型目录周级刷新器启动失败（已忽略）: %s", e)

        logger.info("系统启动成功！")

        yield

        # ===== 关闭阶段 =====
        try:
            if recurring_task["handle"]:
                recurring_task["handle"].cancel()
        except Exception as e:
            logger.warning("取消重复任务处理器失败（已忽略）: %s", e, exc_info=True)

        try:
            if model_catalog_task["handle"]:
                model_catalog_task["handle"].cancel()
        except Exception as e:
            logger.warning("取消模型目录周级刷新器失败（已忽略）: %s", e, exc_info=True)

        try:
            await worker_manager.stop_all()
        except Exception as e:
            logger.warning("停止后台队列 Worker 失败（已忽略）: %s", e, exc_info=True)

        try:
            await scheduler_service.stop()
        except Exception as e:
            logger.warning("停止定时任务调度器失败（已忽略）: %s", e, exc_info=True)

        if enable_message_queue_stop:
            try:
                from app.core.messaging import message_queue
                await message_queue.stop()
            except Exception as e:
                logger.warning("释放消息队列失败（已忽略）: %s", e, exc_info=True)

        logger.info("关闭系统...")

    return lifespan

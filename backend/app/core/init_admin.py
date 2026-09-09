"""
PMI中国AI项目管理社区 - 初始管理员自动创建
在应用启动时调用：若系统中不存在任何超级用户，则使用环境变量配置创建第一个管理员。
"""
import logging

from sqlalchemy import select

from app.config import settings
from app.core.security import get_password_hash
from app.db.session import async_session_maker
from app.models import User
from app.models.system_llm_config import SystemLLMConfig
from app.services.openclaw_service import sync_model_to_openclaw

logger = logging.getLogger("app.init_admin")


def _is_weak_admin_password(password: str) -> bool:
    """判断初始管理员密码是否过弱：空、过短、或缺少字母与数字组合。"""
    if not password:
        return True
    if len(password) < 8:
        return True
    has_alpha = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return not (has_alpha and has_digit)


async def ensure_initial_admin() -> None:
    """确保至少存在一个超级用户；不存在则按配置创建。"""
    try:
        async with async_session_maker() as db:
            result = await db.execute(select(User).where(User.is_superuser.is_(True)))
            if result.scalars().first() is not None:
                return

            # 安全约束：禁止以空密码或弱密码创建初始管理员，避免弱口令被利用。
            if _is_weak_admin_password(settings.INITIAL_ADMIN_PASSWORD):
                logger.error(
                    "初始管理员密码为空或过于简单（需长度≥8 且同时包含字母与数字），"
                    "为安全起见已拒绝以弱口令创建初始管理员。"
                    "请在环境变量 INITIAL_ADMIN_PASSWORD 中设置强密码后重启。"
                )
                raise RuntimeError("初始管理员密码过于简单，拒绝以弱口令启动")

            admin = User(
                email=settings.INITIAL_ADMIN_EMAIL,
                username=settings.INITIAL_ADMIN_USERNAME,
                hashed_password=get_password_hash(settings.INITIAL_ADMIN_PASSWORD),
                full_name=settings.INITIAL_ADMIN_FULL_NAME,
                is_active=True,
                is_superuser=True,
            )
            db.add(admin)
            await db.commit()
            logger.info(
                "已创建初始管理员账号: %s (邮箱: %s)",
                settings.INITIAL_ADMIN_USERNAME,
                settings.INITIAL_ADMIN_EMAIL,
            )
    except RuntimeError:
        # 安全相关的致命错误（如弱口令）必须向上抛出，阻止以弱口令启动。
        raise
    except Exception as e:
        logger.warning("初始管理员创建失败（已忽略）: %s", e)


async def ensure_system_llm_config() -> None:
    """确保系统默认大模型已配置：首次启动自动使用 MiniMax M2.7（内置种子 Key）。"""
    try:
        async with async_session_maker() as db:
            result = await db.execute(select(SystemLLMConfig))
            if result.scalars().first() is not None:
                return

            cfg = SystemLLMConfig(
                provider_name="minimax",
                model_name="MiniMax-M2.7",
                base_url="https://api.minimax.chat/v1",
                api_key=settings.SYSTEM_LLM_SEED_API_KEY,
                temperature=0.7,
                max_tokens=2000,
                is_active=True,
            )
            db.add(cfg)
            await db.commit()
            logger.info("已初始化系统默认大模型：MiniMax M2.7（可在系统设置中修改）")

            # 同步到本地 OpenClaw 配置文件（供 OpenClaw 启动后读取）
            try:
                await                 sync_model_to_openclaw(
                    provider_name=cfg.provider_name,
                    api_key=cfg.api_key,
                    base_url=cfg.base_url,
                    model_name=cfg.model_name,
                    temperature=cfg.temperature,
                    max_tokens=cfg.max_tokens,
                )
            except Exception as e:
                logger.warning("同步模型到 openclaw 失败（已忽略）: %s", e, exc_info=True)
    except Exception as e:
        logger.warning("系统默认大模型初始化失败（已忽略）: %s", e)

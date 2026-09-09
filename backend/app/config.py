"""
PMI中国AI项目管理社区 - 配置文件
支持多环境配置管理
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from typing import List, Optional
from functools import lru_cache
import os
import base64
import secrets
import warnings
import logging

logger = logging.getLogger(__name__)


def _decode_seed_key(encoded: str) -> str:
    """解码系统默认大模型种子 Key。

    说明：该 Key 为公用/共享 Key，仅做去明文 base64 编码（可逆，非保密），
    用于避免在仓库中留存明文，运行时解码后使用。请勿据此认为其具备保密性。
    """
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except Exception as e:
        # 解码失败时原样返回，兼容外部通过环境变量直接传入明文/编码值
        logger.debug("种子 Key 解码失败，按原值返回（兼容明文传入）: %s", e)
        return encoded


def _generate_secret_key() -> str:
    """当未通过环境变量提供 SECRET_KEY 时，生成临时强随机密钥。

    仅用于本地开发（重启即失效）；生产环境务必通过环境变量注入固定强随机值。
    """
    warnings.warn(
        "[配置] SECRET_KEY 未通过环境变量提供，已自动生成临时密钥"
        "（重启将失效，生产环境请通过环境变量设置固定强随机 SECRET_KEY）",
        RuntimeWarning,
        stacklevel=2,
    )
    return secrets.token_hex(32)


def _check_env_file():
    """检查 .env 文件是否存在"""
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(backend_dir, ".env")
    env_example_path = os.path.join(backend_dir, ".env.example")

    if not os.path.exists(env_path):
        if os.path.exists(env_example_path):
            warnings.warn(
                f"\n{'='*60}\n"
                f"[配置警告] 未找到 .env 文件，已从 .env.example 自动创建。\n"
                f"请编辑 {env_path} 文件，填写您的 API 密钥。\n"
                f"{'='*60}\n",
                RuntimeWarning,
                stacklevel=2
            )
            try:
                with open(env_example_path, "r", encoding="utf-8") as f:
                    content = f.read()
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                warnings.warn(f"[配置警告] 自动创建 .env 文件失败: {e}", RuntimeWarning)
        else:
            warnings.warn(
                f"\n{'='*60}\n"
                f"[配置警告] 未找到 .env 文件，且 .env.example 模板也不存在。\n"
                f"系统将使用默认配置运行，但部分功能可能不可用。\n"
                f"{'='*60}\n",
                RuntimeWarning,
                stacklevel=2
            )


# 在模块加载时检查 .env 文件（将 IO 副作用显式化）：
# 1) 可通过环境变量 TWAI_SKIP_ENV_AUTOCREATE=1 关闭，避免导入阶段触发文件写入（如测试/工具导入）；
# 2) 整体包在 try 中，任何 IO 异常都不会导致 import 失败。
if not os.environ.get("TWAI_SKIP_ENV_AUTOCREATE"):
    try:
        _check_env_file()
    except Exception as e:
        logger.warning("模块加载时检查 .env 文件失败（已忽略）: %s", e, exc_info=True)
else:
    logger.debug("已通过 TWAI_SKIP_ENV_AUTOCREATE 跳过 .env 自动创建（import 阶段不做 IO）")


# 弱密钥集合：任何落入此集合的 SECRET_KEY 都视为可公开猜测的占位/弱密钥，
# 不得用于会话签名。生产环境直接拒绝启动；非生产环境由 Settings._harden_secret_key
# 自动替换为随机强密钥，杜绝“公开占位串”被当作 JWT 签名密钥（会话伪造 footgun）。
_WEAK_SECRET_KEYS = {
    "your-secret-key-here-change-in-production",
    "your-super-secret-key-change-in-production",
    "请替换为强随机值",
    "change-me",
    "",
    # 历史发布过的公开占位密钥（曾被写入 .env.example / 安装包），一律视为可公开猜测，
    # 不得用于会话签名。任何部署若仍使用该值，必须在生产环境拒绝启动。
    "91f93c1474a12d48ff10a86754a1b18c0d62ce5fe316edb29918b2f2206ae6f8",
}


class Settings(BaseSettings):
    """应用配置"""

    # 应用信息
    VERSION: str = "1.0.0"
    APP_NAME: str = "PMI中国AI项目管理社区"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")

    # API配置
    API_V1_PREFIX: str = "/api/v1"

    # 安全配置
    # SECRET_KEY 必须来自环境变量；若未提供则自动生成临时强随机密钥（见 _generate_secret_key）。
    SECRET_KEY: str = Field(default_factory=_generate_secret_key, env="SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 初始管理员（首次启动自动创建，仅在系统中无超级用户时生效）
    INITIAL_ADMIN_USERNAME: str = Field(default="admin", env="INITIAL_ADMIN_USERNAME")
    INITIAL_ADMIN_PASSWORD: str = Field(default="", env="INITIAL_ADMIN_PASSWORD")
    INITIAL_ADMIN_EMAIL: str = Field(default="admin@tongweizx.com", env="INITIAL_ADMIN_EMAIL")
    INITIAL_ADMIN_FULL_NAME: str = Field(default="系统管理员", env="INITIAL_ADMIN_FULL_NAME")

    # 是否使用 Alembic 迁移（生产推荐开启；关闭时用 create_all 兜底）
    DB_MIGRATE: bool = Field(default=False, env="DB_MIGRATE")

    # 数据库配置
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/tw_ai_pms",
        env="DATABASE_URL"
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis配置
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    REDIS_MAX_CONNECTIONS: int = 50

    # CORS配置
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173",
        env="CORS_ORIGINS"
    )

    @property
    def cors_origins_list(self) -> List[str]:
        """将CORS_ORIGINS字符串转换为列表"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    # AI配置
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")
    ANTHROPIC_API_KEY: str = Field(default="", env="ANTHROPIC_API_KEY")
    MINIMAX_API_KEY: str = Field(default="", env="MINIMAX_API_KEY")
    DEEPSEEK_API_KEY: str = Field(default="", env="DEEPSEEK_API_KEY")
    # RAG 嵌入模型配置（本地免费模型，默认 BGE-M3，无需任何 API Key）
    RAG_EMBEDDING_PROVIDER: str = Field(default="local", env="RAG_EMBEDDING_PROVIDER")
    RAG_LOCAL_MODEL: str = Field(default="BAAI/bge-base-zh", env="RAG_LOCAL_MODEL")

    # 系统默认大模型初始化种子 Key（可选）。
    # 默认留空，必须由环境变量 SYSTEM_LLM_SEED_API_KEY 注入；
    # _decode_seed_key 仍保留以兼容外部以 base64 形式传入的值，
    # 但本仓库不再内嵌任何真实 Key 字面量。
    SYSTEM_LLM_SEED_API_KEY: str = Field(default="", env="SYSTEM_LLM_SEED_API_KEY")

    # 百度文心一言配置
    BAIDU_API_KEY: str = Field(default="", env="BAIDU_API_KEY")
    BAIDU_SECRET_KEY: str = Field(default="", env="BAIDU_SECRET_KEY")

    # 阿里通义千问配置
    ALIYUN_API_KEY: str = Field(default="", env="ALIYUN_API_KEY")

    # 腾讯混元配置
    TENCENT_API_KEY: str = Field(default="", env="TENCENT_API_KEY")

    # 智谱GLM配置
    ZHIPU_API_KEY: str = Field(default="", env="ZHIPU_API_KEY")

    # Moonshot Kimi配置
    MOONSHOT_API_KEY: str = Field(default="", env="MOONSHOT_API_KEY")

    # 通义千问v2配置
    QWEN_API_KEY: str = Field(default="", env="QWEN_API_KEY")

    # 硅基流动配置
    SILICONFLOW_API_KEY: str = Field(default="", env="SILICONFLOW_API_KEY")

    # 自定义OpenAI兼容API配置
    # OpenClaw本地AI助手配置
    OPENCLAW_API_BASE: str = Field(default="http://localhost:9090", env="OPENCLAW_API_BASE")
    OPENCLAW_ASSISTANT_ID: str = Field(default="default", env="OPENCLAW_ASSISTANT_ID")
    OPENCLAW_ENABLED: bool = Field(default=False, env="OPENCLAW_ENABLED")

    OPENAI_COMPATIBLE_API_KEY: str = Field(default="", env="OPENAI_COMPATIBLE_API_KEY")
    OPENAI_COMPATIBLE_BASE_URL: str = Field(default="", env="OPENAI_COMPATIBLE_BASE_URL")

    # LLM模型配置
    LLM_MODEL: str = "gpt-4-turbo-preview"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2000

    # 飞书配置
    FEISHU_APP_ID: str = Field(default="", env="FEISHU_APP_ID")
    FEISHU_APP_SECRET: str = Field(default="", env="FEISHU_APP_SECRET")

    # 钉钉配置（应用级凭证，用于审批等开放接口）
    DINGTALK_APP_KEY: str = Field(default="", env="DINGTALK_APP_KEY")
    DINGTALK_APP_SECRET: str = Field(default="", env="DINGTALK_APP_SECRET")

    # 企业微信配置（企业级凭证，用于通讯录/审批等接口）
    WECOM_CORP_ID: str = Field(default="", env="WECOM_CORP_ID")
    WECOM_CORP_SECRET: str = Field(default="", env="WECOM_CORP_SECRET")
    WECOM_AGENT_ID: str = Field(default="", env="WECOM_AGENT_ID")

    # Zapier Webhook 签名密钥（配置了才会校验 X-Zapier-Signature）
    ZAPIER_WEBHOOK_SECRET: str = Field(default="", env="ZAPIER_WEBHOOK_SECRET")

    # 文件存储
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS: set = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "txt", "md"}

    # 邮件配置
    SMTP_HOST: str = Field(default="smtp.gmail.com", env="SMTP_HOST")
    SMTP_PORT: int = 587
    SMTP_USER: str = Field(default="", env="SMTP_USER")
    SMTP_PASSWORD: str = Field(default="", env="SMTP_PASSWORD")
    EMAILS_FROM: str = "noreply@tongweizx.com"

    # Celery配置
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2", env="CELERY_RESULT_BACKEND")

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # 分页配置
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # 缓存配置
    CACHE_TTL: int = 300  # 5分钟
    CACHE_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",  # 纵深防御：环境中存在未声明键（如历史遗留 MINIMAX_MODEL）时忽略而非崩溃启动
    )

    @model_validator(mode="after")
    def _harden_secret_key(self):
        """兜底加固 SECRET_KEY：

        - 若 SECRET_KEY 为占位/弱密钥或长度不足 32 位：
          * 生产环境：直接抛错，禁止以可猜测密钥启动（避免会话伪造）。
          * 非生产环境：自动替换为随机强密钥，杜绝“公开占位串”被当作
            会话签名密钥（即便 .env 由 .env.example 再生亦如此）。
        """
        weak = self.SECRET_KEY in _WEAK_SECRET_KEYS or len(self.SECRET_KEY or "") < 32
        if weak:
            if self.ENVIRONMENT == "production":
                raise RuntimeError(
                    "生产环境必须显式设置强随机 SECRET_KEY（openssl rand -hex 32）"
                )
            # 非生产：自动替换为随机强密钥，杜绝“公开占位串”被当作会话签名密钥
            self.SECRET_KEY = secrets.token_hex(32)
        return self

    def validate_config(self) -> dict:
        """
        验证必要配置是否已设置
        返回验证结果报告
        """
        errors = []
        warnings_list = []

        # 检查 SECRET_KEY 强度（弱密钥会导致签名伪造/会话劫持）
        WEAK_SECRET_KEYS: set = {
            "your-secret-key-here-change-in-production",
            "your-super-secret-key-change-in-production",
            "请替换为强随机值",
            "change-me",
            "",
            "91f93c1474a12d48ff10a86754a1b18c0d62ce5fe316edb29918b2f2206ae6f8",
        }
        if self.SECRET_KEY in WEAK_SECRET_KEYS or len(self.SECRET_KEY or "") < 32:
            msg = (
                "SECRET_KEY 为弱密钥或长度不足 32 位，生产环境必须使用强随机值"
                "（openssl rand -hex 32 生成并安全保管）"
            )
            if self.ENVIRONMENT == "production":
                errors.append(msg)
            else:
                warnings_list.append(msg)

        # 检查初始管理员密码强度（弱口令会导致越权风险）
        WEAK_ADMIN_PASSWORDS: set = {
            "admin123", "password", "12345678", "admin", "root", "changeme",
        }
        _pwd = self.INITIAL_ADMIN_PASSWORD or ""
        _pwd_weak = (
            len(_pwd) < 12
            or _pwd in WEAK_ADMIN_PASSWORDS
            or not (
                any(c.isalpha() for c in _pwd)
                and any(c.isdigit() for c in _pwd)
                and any(not c.isalnum() for c in _pwd)
            )
        )
        if _pwd_weak:
            msg = (
                "INITIAL_ADMIN_PASSWORD 为弱口令（需长度≥12 且同时包含字母、数字与特殊字符），"
                "生产环境请设置强密码"
            )
            if self.ENVIRONMENT == "production":
                errors.append(msg)
            else:
                warnings_list.append(msg)

        # 检查数据库配置
        if not self.DATABASE_URL:
            errors.append("DATABASE_URL 未配置")

        # 检查至少一个AI API Key
        ai_keys = {
            "OpenAI": self.OPENAI_API_KEY,
            "DeepSeek": self.DEEPSEEK_API_KEY,
            "Anthropic": self.ANTHROPIC_API_KEY,
            "百度文心": self.BAIDU_API_KEY,
            "阿里通义": self.ALIYUN_API_KEY,
            "腾讯混元": self.TENCENT_API_KEY,
            "智谱GLM": self.ZHIPU_API_KEY,
            "Moonshot": self.MOONSHOT_API_KEY,
            "通义千问": self.QWEN_API_KEY,
            "硅基流动": self.SILICONFLOW_API_KEY,
            "OpenAI兼容": self.OPENAI_COMPATIBLE_API_KEY,
        }

        configured_providers = [name for name, key in ai_keys.items() if key and key.strip()]

        if not configured_providers:
            warnings_list.append("未配置任何 AI API Key，AI 功能将不可用")
        else:
            # 检查百度特殊配置
            if self.BAIDU_API_KEY and not self.BAIDU_SECRET_KEY:
                warnings_list.append("BAIDU_API_KEY 已配置但 BAIDU_SECRET_KEY 缺失")
            if self.OPENAI_COMPATIBLE_API_KEY and not self.OPENAI_COMPATIBLE_BASE_URL:
                warnings_list.append("OPENAI_COMPATIBLE_API_KEY 已配置但 OPENAI_COMPATIBLE_BASE_URL 缺失")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings_list,
            "configured_ai_providers": configured_providers,
            "database_type": "SQLite" if "sqlite" in self.DATABASE_URL.lower() else "PostgreSQL",
        }

    def get_available_ai_providers(self) -> List[dict]:
        """获取已配置的AI Provider列表"""
        providers = []

        provider_configs = [
            ("openai", "OpenAI", self.OPENAI_API_KEY),
            ("deepseek", "DeepSeek", self.DEEPSEEK_API_KEY),
            ("anthropic", "Anthropic Claude", self.ANTHROPIC_API_KEY),
            ("baidu", "百度文心一言", self.BAIDU_API_KEY),
            ("aliyun", "阿里通义千问", self.ALIYUN_API_KEY),
            ("tencent", "腾讯混元", self.TENCENT_API_KEY),
            ("zhipu", "智谱GLM", self.ZHIPU_API_KEY),
            ("moonshot", "Moonshot Kimi", self.MOONSHOT_API_KEY),
            ("qwen", "通义千问", self.QWEN_API_KEY),
            ("siliconflow", "硅基流动", self.SILICONFLOW_API_KEY),
            ("openai_compatible", "OpenAI兼容", self.OPENAI_COMPATIBLE_API_KEY),
        ]

        for key, name, api_key in provider_configs:
            if api_key and api_key.strip():
                providers.append({
                    "key": key,
                    "name": name,
                    "configured": True,
                })

        return providers


@lru_cache()
def get_settings() -> Settings:
    """获取配置实例（单例）"""
    return Settings()


settings = get_settings()

# 启动时验证配置
_config_report = settings.validate_config()
if _config_report["warnings"]:
    for warning in _config_report["warnings"]:
        warnings.warn(f"[配置] {warning}", RuntimeWarning)
if _config_report["errors"]:
    for error in _config_report["errors"]:
        warnings.warn(f"[配置错误] {error}", RuntimeWarning)

# 生产环境下若存在硬失败项（弱密钥/弱口令等），直接终止进程，避免带病上线
if settings.ENVIRONMENT == "production" and _config_report["errors"]:
    raise RuntimeError(
        "生产环境配置校验失败，进程退出：\n"
        + "\n".join(f" - {e}" for e in _config_report["errors"])
    )

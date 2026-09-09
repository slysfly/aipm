"""
PMI中国AI项目管理社区 - LLM配置API
支持用户级大模型配置管理

[PMBOK KA: 跨领域 (Cross-area) — LLM模型配置、AI引擎管理]
对应PMI第6版标准：AI资源配置

[CPMAI Phase: CPMAI Phase: Model Development | Domain: AI Fundamentals — LLM模型配置管理]"""

import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.llm_config import LLMConfig
from app.schemas.llm_config import (
    LLMConfigCreate,
    LLMConfigUpdate,
    LLMConfigResponse,
    LLMConfigListResponse,
    LLMProviderInfo,
    LLMProvidersResponse,
    LLMConfigTestRequest,
    LLMConfigTestResponse,
)
from app.core.ai_engine import ai_engine
from app.core.security import get_current_user
from app.models import User

router = APIRouter()

# Provider元数据定义
# value_picks 是 AI 性价比推荐：每项 {"tag":"性价比首选|高性能|长文本|推理","model":"...","reason":"..."}
# 前端按 tag 渲染「AI 智能推荐」卡片，附一键填入按钮
PROVIDER_METADATA = {
    "openai": LLMProviderInfo(
        name="openai",
        display_name="OpenAI",
        description="GPT-5.6 / GPT-5.5 / GPT-5.4 系列模型（2026-07 最新）",
        default_base_url="https://api.openai.com/v1",
        default_model="gpt-5.6-luna",
        supported_models=["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.1", "o3-pro"],
        icon="🇺🇸",
        value_picks=[
            {"tag": "性价比首选", "model": "gpt-5.6-luna", "reason": "GPT-5.6 均衡版，1M 上下文，价格约为旗舰 Sol 的 1/4；适合 WBS 生成、风险预测、对话等 90% 场景。"},
            {"tag": "高性能", "model": "gpt-5.6-sol", "reason": "GPT-5.6 旗舰，最强推理与多模态；重要决策、复杂分析用。"},
            {"tag": "推理强", "model": "o3-pro", "reason": "深度推理专用；项目博弈、风险推演、复杂决策推荐；响应较慢。"},
        ],
        config_advice="1) API Key 在 platform.openai.com 获取，格式 sk- 开头；\n2) 国内直连常被墙，建议走合规代理或换国产模型；\n3) gpt-5.6-luna 是当前综合性价比最高的 OpenAI 模型。",
    ),
    "deepseek": LLMProviderInfo(
        name="deepseek",
        display_name="DeepSeek",
        description="DeepSeek V4 / V3.2 / R2 / Coder 2.0 系列（2026-07 最新）",
        default_base_url="https://api.deepseek.com/v1",
        default_model="deepseek-v4-flash",
        supported_models=["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v3.2", "deepseek-v3.2-speciale", "deepseek-r2", "deepseek-coder-2.0"],
        icon="🐳",
        value_picks=[
            {"tag": "性价比首选", "model": "deepseek-v4-flash", "reason": "V4 极速版，价格极低，中文能力强；适合 WBS / 风险 / 对话等 90% 场景。"},
            {"tag": "高性能", "model": "deepseek-v4-pro", "reason": "V4 旗舰，综合能力最强；项目分析、重要决策推荐。"},
            {"tag": "推理强", "model": "deepseek-r2", "reason": "R2 推理深度媲美 o3-pro，价格仍极低；复杂分析推荐。"},
            {"tag": "代码强", "model": "deepseek-coder-2.0", "reason": "代码生成/重构专用；技术债务、代码评审场景。"},
        ],
        config_advice="1) API Key 在 platform.deepseek.com 申请；\n2) 价格极低，国内直连通畅；\n3) 推荐 deepseek-v4-flash 为主，复杂分析切 deepseek-v4-pro / deepseek-r2。",
    ),
    "anthropic": LLMProviderInfo(
        name="anthropic",
        display_name="Anthropic Claude",
        description="Claude Fable 5 / Opus 4.8 / Sonnet 5 / Haiku 4.5（2026-07 最新）",
        default_base_url="https://api.anthropic.com/v1",
        default_model="claude-haiku-4-5",
        supported_models=["claude-fable-5", "claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
        icon="🧠",
        supports_models_endpoint=False,  # Anthropic 用 /v1/messages 而非 /v1/models
        value_picks=[
            {"tag": "性价比首选", "model": "claude-haiku-4-5", "reason": "200K 上下文，速度最快、价格最低；日常 WBS/对话首选。"},
            {"tag": "高性能", "model": "claude-sonnet-5", "reason": "200K 长上下文 + 顶级推理；项目分析/风险评估综合最强。"},
            {"tag": "深度推理", "model": "claude-opus-4-8", "reason": "Opus 推理能力天花板；极重要决策用，价格高。"},
            {"tag": "旗舰", "model": "claude-fable-5", "reason": "Claude 最新旗舰 Fable 5，综合能力最强。"},
        ],
        config_advice="1) API Key 在 console.anthropic.com 获取；\n2) Anthropic 走 /v1/messages 协议（前端 fetch 走 OpenAI 兼容层）；\n3) 国内直连需代理。",
    ),
    "baidu": LLMProviderInfo(
        name="baidu",
        display_name="百度文心一言",
        description="百度文心 ERNIE 5.1 / 5.0 / X1.1（2026-07 最新）",
        default_base_url="https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat",
        default_model="ernie-5.1",
        supported_models=["ernie-5.1", "ernie-5.0", "ernie-x1.1"],
        requires_secret=True,  # 需要 AK/SK
        supports_models_endpoint=False,  # 文心 RPC 协议，无 /v1/models
        icon="🐾",
        value_picks=[
            {"tag": "性价比首选", "model": "ernie-5.1", "reason": "文心 5.1（2026-05 发布），速度快、价格亲民；日常任务首选。"},
            {"tag": "高性能", "model": "ernie-5.0", "reason": "文心 5.0 全模态 2.4T，综合能力最强；复杂分析推荐。"},
            {"tag": "推理强", "model": "ernie-x1.1", "reason": "X1.1 深度思考模型；复杂推理场景。"},
        ],
        config_advice="1) 需在 cloud.baidu.com 创建应用获取 AK/SK；\n2) 协议为百度自研 RPC，非 OpenAI 兼容；\n3) 鉴权通过 access_token 走两步换 token 流程。",
    ),
    "aliyun": LLMProviderInfo(
        name="aliyun",
        display_name="阿里通义千问",
        description="阿里云 Qwen3.7 / Qwen3.6 / Qwen3.5 系列（2026-07 最新）",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3.6-plus",
        supported_models=["qwen3.7-max", "qwen3.7-plus", "qwen3.6-max", "qwen3.6-plus", "qwen3.6-flash", "qwen3.5-max", "qwen3.5-plus", "qwen3.5-flash", "qwen3-coder", "qwen-long"],
        icon="☁️",
        value_picks=[
            {"tag": "性价比首选", "model": "qwen3.6-flash", "reason": "Qwen3.6 极速版，价格最低、速度快；WBS 生成、对话等高频任务首选。"},
            {"tag": "高性能", "model": "qwen3.7-max", "reason": "Qwen3.7 旗舰，综合最强；项目分析推荐。"},
            {"tag": "长文本", "model": "qwen-long", "reason": "支持 1M token 上下文；知识库全文分析、长文档摘要。"},
            {"tag": "代码强", "model": "qwen3-coder", "reason": "代码生成/重构专用；技术债务、代码评审场景。"},
        ],
        config_advice="1) API Key 在 dashscope.console.aliyun.com 创建；\n2) OpenAI 兼容模式走 /compatible-mode/v1；\n3) 国内直连通畅，性价比突出。",
    ),
    "tencent": LLMProviderInfo(
        name="tencent",
        display_name="腾讯混元",
        description="腾讯混元 Hy3 / Turbo S / T1 / Large（2026-07 最新）",
        default_base_url="https://hunyuan.tencentcloudapi.com/v1",
        default_model="hunyuan-turbo-s",
        supported_models=["hunyuan-hy3-preview", "hunyuan-turbo-s", "hunyuan-t1", "hunyuan-large"],
        icon="🐧",
        supports_models_endpoint=False,  # 腾讯云 hunyuan 走 API 3.0 鉴权
        value_picks=[
            {"tag": "性价比首选", "model": "hunyuan-turbo-s", "reason": "Turbo S 快思考模型，能力接近 T1、延迟与成本更低；日常首选。"},
            {"tag": "高性能", "model": "hunyuan-t1", "reason": "T1 慢思考推理模型；复杂分析、深度推理推荐。"},
            {"tag": "长文本", "model": "hunyuan-large", "reason": "万亿参数 MoE，长上下文；长文档/知识库分析。"},
            {"tag": "旗舰", "model": "hunyuan-hy3-preview", "reason": "混元 Hy3 预览旗舰（2026-04, 262K 上下文）。"},
        ],
        config_advice="1) 需在 cloud.tencent.com 开通混元 + 获取 SecretId/SecretKey；\n2) 走 TC3-HMAC_SHA256 鉴权；\n3) 国内直连通畅。",
    ),
    "zhipu": LLMProviderInfo(
        name="zhipu",
        display_name="智谱GLM",
        description="智谱 AI GLM-5.2 / 5.1 / 5 / 4.7 系列（2026-07 最新）",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-5.2",
        supported_models=["glm-5.2", "glm-5.1", "glm-5", "glm-4.7-flash", "glm-4.7", "glm-4.6v"],
        icon="🧊",
        value_picks=[
            {"tag": "性价比首选", "model": "glm-4.7-flash", "reason": "免费档/极低价，速度极快；WBS/对话首选。"},
            {"tag": "高性能", "model": "glm-5.2", "reason": "GLM-5.2 最新旗舰（1M 上下文），综合能力最强；项目分析/风险评估。"},
            {"tag": "多模态", "model": "glm-4.6v", "reason": "支持图像理解；项目截图/图表分析。"},
        ],
        config_advice="1) API Key 在 open.bigmodel.cn 获取；\n2) glm-4.7-flash 有免费额度，性价比极高；\n3) 国内直连通畅。",
    ),
    "moonshot": LLMProviderInfo(
        name="moonshot",
        display_name="Moonshot Kimi",
        description="Moonshot Kimi K3 / K2.7 / K2.6 系列（2026-07 最新）",
        default_base_url="https://api.moonshot.cn/v1",
        default_model="kimi-k3",
        supported_models=["kimi-k3", "kimi-k2.7-code", "kimi-k2.6", "kimi-k2.5", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "moonshot-v1-auto"],
        icon="🌙",
        value_picks=[
            {"tag": "性价比首选", "model": "kimi-k3", "reason": "Kimi K3 最新旗舰（2.8T, 1M 上下文），价格亲民；项目全场景通吃。"},
            {"tag": "长文本", "model": "moonshot-v1-128k", "reason": "128K 上下文；知识库全文、长文档分析强项。"},
            {"tag": "代码强", "model": "kimi-k2.7-code", "reason": "K2.7 代码专用；代码生成/重构场景。"},
        ],
        config_advice="1) API Key 在 platform.moonshot.cn 申请；\n2) 长文本场景首选 128k / K3；\n3) 国内直连通畅。",
    ),
    "siliconflow": LLMProviderInfo(
        name="siliconflow",
        display_name="硅基流动",
        description="SiliconFlow 模型聚合平台（2026-07 最新：DeepSeek V4 / Qwen3.6 / GLM-5.2 / Kimi-K2.7 等）",
        default_base_url="https://api.siliconflow.cn/v1",
        default_model="Qwen/Qwen3.6-7B-Instruct",
        supported_models=[
            "deepseek-ai/DeepSeek-V4-Pro",
            "deepseek-ai/DeepSeek-V4-Flash",
            "Qwen/Qwen3.6-72B-Instruct",
            "Qwen/Qwen3.6-32B-Instruct",
            "Qwen/Qwen3.6-7B-Instruct",
            "Zhipu/GLM-5.2",
            "Zhipu/GLM-5.1",
            "moonshotai/Kimi-K2.7",
            "moonshotai/Kimi-K2.6",
            "MiniMax/MiniMax-M2.5",
            "LongCat/LongCat-2.0",
        ],
        icon="🧬",
        value_picks=[
            {"tag": "性价比首选", "model": "Qwen/Qwen3.6-7B-Instruct", "reason": "价格极低，速度快；高频轻量任务。"},
            {"tag": "高性能", "model": "deepseek-ai/DeepSeek-V4-Pro", "reason": "V4 Pro 顶级开源；综合能力强，价格仅为 GPT 旗舰的零头。"},
            {"tag": "深度推理", "model": "moonshotai/Kimi-K2.7", "reason": "Kimi K2.7 开源推理强模型；复杂分析推荐。"},
        ],
        config_advice="1) API Key 在 cloud.siliconflow.cn 获取；\n2) 价格极低，国内直连；\n3) 适合跑大批量 WBS/分析任务。",
    ),
    "minimax": LLMProviderInfo(
        name="minimax",
        display_name="MiniMax 稀宇",
        description="MiniMax M3 / M2.7 / M2.5 系列（2026-07 最新），OpenAI 兼容协议",
        default_base_url="https://api.minimax.chat/v1",
        default_model="MiniMax-M3",
        supported_models=["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.1", "MiniMax-M2", "MiniMax-Text-01", "abab6.5s-chat"],
        icon="🦊",
        value_picks=[
            {"tag": "性价比首选", "model": "MiniMax-M3", "reason": "2026-06 最新 Frontier Coding，强推理 + 1M 长上下文，价格亲民；项目全场景通吃。"},
            {"tag": "长文本", "model": "MiniMax-Text-01", "reason": "1M token 超长上下文；知识库全文、长文档分析强项。"},
            {"tag": "通用对话", "model": "abab6.5s-chat", "reason": "对话轻量档；高频低延迟场景。"},
        ],
        config_advice=(
            "1) API Key 在 MiniMax 开放平台获取，格式以 sk- 开头；\n"
            "2) Base URL 默认 https://api.minimax.chat/v1（OpenAI 兼容）；\n"
            "3) 旧版账号可能需要填写 GroupId（在请求头 GroupId 中传递），新版 API Key 无需；\n"
            "4) M3 为强推理模型，建议 temperature 0.3~0.7、max_tokens 2000+；\n"
            "5) 本系统已将其设为默认大模型，配置后所有 AI 能力（WBS/分析/对话）将自动使用。"
        ),
    ),
    "openai_compatible": LLMProviderInfo(
        name="openai_compatible",
        display_name="自定义OpenAI兼容",
        description="兼容OpenAI API格式的自定义模型",
        default_base_url="http://localhost:8000/v1",
        default_model="default-model",
        supported_models=["custom-model"],
        icon="🔌",
        supports_models_endpoint=True,  # 用户自填的兼容端点
        value_picks=[
            {"tag": "自定义", "model": "custom-model", "reason": "请将模型名称改为你的端点实际支持的模型 ID。"},
        ],
        config_advice="1) Base URL 改为你的端点（如本地 Ollama / vLLM / 自建代理）；\n2) 模型名称填写你的端点支持的真实 ID；\n3) API Key 若端点免鉴权可留空。",
    ),
}


def _get_current_user_id(current_user: User) -> str:
    return current_user.id


@router.get("/", response_model=LLMConfigListResponse)
async def get_llm_configs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _get_current_user_id(current_user)
    result = await db.execute(
        select(LLMConfig).where(LLMConfig.user_id == user_id).order_by(LLMConfig.created_at.desc())
    )
    configs = result.scalars().all()
    return LLMConfigListResponse(
        items=[LLMConfigResponse.model_validate(c) for c in configs],
        total=len(configs),
    )


@router.post("/", response_model=LLMConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_llm_config(
    config: LLMConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _get_current_user_id(current_user)

    # 检查是否已存在相同Provider的配置
    result = await db.execute(
        select(LLMConfig).where(
            and_(LLMConfig.user_id == user_id, LLMConfig.provider_name == config.provider_name)
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{config.provider_name}' 的配置已存在，请更新现有配置",
        )

    # 如果是第一个配置，设为默认
    result = await db.execute(select(func.count()).where(LLMConfig.user_id == user_id))
    count = result.scalar()
    is_default = count == 0

    db_config = LLMConfig(
        user_id=user_id,
        provider_name=config.provider_name,
        model_name=config.model_name,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        is_default=is_default,
        is_enabled=config.is_enabled,
    )
    db_config.api_key = config.api_key or ""
    db_config.base_url = config.base_url

    db.add(db_config)
    await db.commit()
    await db.refresh(db_config)

    return LLMConfigResponse.model_validate(db_config)


@router.put("/{config_id}", response_model=LLMConfigResponse)
async def update_llm_config(
    config_id: str,
    config: LLMConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _get_current_user_id(current_user)

    result = await db.execute(
        select(LLMConfig).where(
            and_(LLMConfig.id == config_id, LLMConfig.user_id == user_id)
        )
    )
    db_config = result.scalar_one_or_none()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    update_data = config.model_dump(exclude_unset=True)

    # 单独处理api_key加密
    if "api_key" in update_data:
        api_key = update_data.pop("api_key")
        if api_key:
            db_config.api_key = api_key

    for field, value in update_data.items():
        setattr(db_config, field, value)

    await db.commit()
    await db.refresh(db_config)

    return LLMConfigResponse.model_validate(db_config)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _get_current_user_id(current_user)

    result = await db.execute(
        select(LLMConfig).where(
            and_(LLMConfig.id == config_id, LLMConfig.user_id == user_id)
        )
    )
    db_config = result.scalar_one_or_none()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    was_default = db_config.is_default
    await db.delete(db_config)
    await db.commit()

    # 如果删除的是默认配置，将剩余第一个设为默认
    if was_default:
        result = await db.execute(
            select(LLMConfig).where(LLMConfig.user_id == user_id).order_by(LLMConfig.created_at.asc())
        )
        first = result.scalar_one_or_none()
        if first:
            first.is_default = True
            await db.commit()

    return None


@router.post("/{config_id}/set-default", response_model=LLMConfigResponse)
async def set_default_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _get_current_user_id(current_user)

    # 清除该用户所有默认配置
    result = await db.execute(select(LLMConfig).where(LLMConfig.user_id == user_id))
    configs = result.scalars().all()
    for c in configs:
        c.is_default = False

    # 设置新的默认配置
    result = await db.execute(
        select(LLMConfig).where(
            and_(LLMConfig.id == config_id, LLMConfig.user_id == user_id)
        )
    )
    db_config = result.scalar_one_or_none()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    db_config.is_default = True
    await db.commit()
    await db.refresh(db_config)

    return LLMConfigResponse.model_validate(db_config)


@router.post("/{config_id}/test", response_model=LLMConfigTestResponse)
async def test_llm_config(
    config_id: str,
    request: LLMConfigTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = _get_current_user_id(current_user)

    result = await db.execute(
        select(LLMConfig).where(
            and_(LLMConfig.id == config_id, LLMConfig.user_id == user_id)
        )
    )
    db_config = result.scalar_one_or_none()
    if not db_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在")

    if not db_config.is_enabled:
        return LLMConfigTestResponse(success=False, message="配置已禁用")

    try:
        start_time = time.time()

        # 动态注册Provider并测试
        provider = ai_engine.create_provider_from_config(
            provider_name=db_config.provider_name,
            api_key=db_config.api_key,
            base_url=db_config.base_url,
            model_name=db_config.model_name,
            temperature=db_config.temperature,
            max_tokens=db_config.max_tokens,
        )

        messages = [{"role": "user", "content": request.message}]
        response_text = await provider.chat(messages)

        latency_ms = int((time.time() - start_time) * 1000)

        return LLMConfigTestResponse(
            success=True,
            message="连接测试成功",
            response=response_text[:500] if response_text else None,
            latency_ms=latency_ms,
        )
    except Exception as e:
        return LLMConfigTestResponse(
            success=False,
            message=f"连接测试失败: {str(e)}",
        )


@router.get("/providers", response_model=LLMProvidersResponse)
async def get_providers():
    return LLMProvidersResponse(providers=list(PROVIDER_METADATA.values()))

"""
PMI中国AI项目管理社区 - 系统级 LLM 配置 API（管理员）
管理员在“系统设置 > 大模型设置”中配置系统默认大模型，全局 AI 能力将自动使用。

[PMBOK KA: 跨领域 (Cross-area) — 系统LLM配置]
对应PMI第6版标准：系统LLM配置管理

[CPMAI Phase: CPMAI Phase: Model Development | Domain: AI Fundamentals — 系统级LLM配置]"""

import time
import logging
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.system_llm_config import SystemLLMConfig
from app.schemas.system_llm_config import (
    SystemLLMConfigUpsert,
    SystemLLMConfigResponse,
    SystemLLMConfigTestRequest,
    SystemLLMConfigTestResponse,
    SystemLLMProvidersResponse,
    SystemLLMProviderInfo,
    SystemLLMFetchModelsRequest,
    SystemLLMFetchModelsResponse,
)
from app.core.ai_engine import ai_engine
from app.services.ai_service import ai_service
from app.core.security import require_superuser, get_current_user
from app.models import User
from app.api.v1.llm_configs import PROVIDER_METADATA
from app.services.model_catalog_service import (
    is_fresh,
    get_provider_entry,
    refresh_all,
    cache_provider_result,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/llm-config", response_model=SystemLLMConfigResponse)
async def get_system_llm_config(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_superuser),
):
    cfg = await _load_config(db)
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未配置系统大模型")
    return SystemLLMConfigResponse(**cfg.to_dict(include_api_key=False))


@router.put("/llm-config", response_model=SystemLLMConfigResponse)
async def upsert_system_llm_config(
    payload: SystemLLMConfigUpsert,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_superuser),
):
    cfg = await _load_config(db)
    if cfg is None:
        cfg = SystemLLMConfig()
        db.add(cfg)

    cfg.provider_name = payload.provider_name
    cfg.base_url = payload.base_url
    cfg.model_name = payload.model_name
    cfg.temperature = payload.temperature
    cfg.max_tokens = payload.max_tokens
    cfg.is_active = payload.is_active
    # 仅当传入非空 key 时更新（保证留空不改密文）
    if payload.api_key:
        cfg.api_key = payload.api_key

    await db.commit()
    await db.refresh(cfg)

    # 让全局 AI 能力立即使用新配置
    ai_service.invalidate_cache()

    return SystemLLMConfigResponse(**cfg.to_dict(include_api_key=False))


@router.post("/llm-config/test", response_model=SystemLLMConfigTestResponse)
async def test_system_llm_config(
    request: SystemLLMConfigTestRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_superuser),
):
    cfg = await _load_config(db)
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未配置系统大模型")
    if not cfg.api_key:
        return SystemLLMConfigTestResponse(success=False, message="未配置 API Key")

    try:
        start = time.time()
        provider = ai_engine.create_provider_from_config(
            provider_name=cfg.provider_name,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model_name=cfg.model_name,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        text = await provider.chat([{"role": "user", "content": request.message}])
        latency = int((time.time() - start) * 1000)
        return SystemLLMConfigTestResponse(
            success=True, message="连接成功", response=text[:500], latency_ms=latency
        )
    except Exception as e:
        return SystemLLMConfigTestResponse(success=False, message=f"连接失败：{str(e)}")


@router.get("/llm-config/providers", response_model=SystemLLMProvidersResponse)
async def list_providers(_: User = Depends(require_superuser)):
    providers = [
        SystemLLMProviderInfo(**p.model_dump())
        for p in PROVIDER_METADATA.values()
    ]
    return SystemLLMProvidersResponse(providers=providers)


@router.post("/llm-config/fetch-models", response_model=SystemLLMFetchModelsResponse)
async def fetch_provider_models(
    payload: SystemLLMFetchModelsRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_superuser),
):
    """
    用 API Key 调厂商 OpenAI 协议 /v1/models 端点，实时拉取该厂商正在服务的模型清单。

    适用条件：
    - 厂商兼容 OpenAI Chat Completions 协议（OpenAI / DeepSeek / MiniMax / SiliconFlow / Moonshot / Zhipu / 自定义兼容端点）
    - API Key 有效（留空时自动用系统已存的密文）
    - 厂商开放了 /v1/models 列表端点

    失败/不支持时回退到 PROVIDER_METADATA 的 supported_models 静态列表。
    """
    provider_meta = PROVIDER_METADATA.get(payload.provider_name)
    if not provider_meta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未知厂商：{payload.provider_name}",
        )

    # 静态兜底列表（缓存/实时都失败时回退）
    static_fallback = provider_meta.supported_models or ([provider_meta.default_model] if provider_meta.default_model else [])

    # ── 优先读本地周级缓存（避免每次打开设置都打厂商 API） ──
    if not payload.force and is_fresh(payload.provider_name):
        entry = get_provider_entry(payload.provider_name)
        if entry:
            logger.info("fetch-models: %s 命中本地缓存（source=%s）", payload.provider_name, entry.get("source"))
            return SystemLLMFetchModelsResponse(
                provider_name=payload.provider_name,
                models=entry["models"],
                source=entry["source"],
                raw_count=entry.get("raw_count", 0),
                static_fallback=static_fallback,
            )

    # API Key 留空 → 用系统已存的密文（需 superuser 已配置过）
    api_key = (payload.api_key or "").strip()
    if not api_key:
        existing = await _load_config(db)
        if existing and existing.provider_name == payload.provider_name and existing.api_key:
            api_key = existing.api_key
        else:
            # 还没系统配置过：返回静态列表即可，不阻塞 UI
            static_fallback = provider_meta.supported_models or ([provider_meta.default_model] if provider_meta.default_model else [])
            return SystemLLMFetchModelsResponse(
                provider_name=payload.provider_name,
                models=static_fallback,
                source="fallback",
                raw_count=0,
                static_fallback=static_fallback,
            )

    base_url = (payload.base_url or provider_meta.default_base_url or "").rstrip("/")
    if not base_url:
        return SystemLLMFetchModelsResponse(
            provider_name=payload.provider_name,
            models=provider_meta.supported_models or [provider_meta.default_model],
            source="fallback",
            raw_count=0,
            static_fallback=provider_meta.supported_models or [provider_meta.default_model],
        )

    # 拼接 /v1/models：base_url 可能是 .../v1 也可能是裸域名，统一保证以 /v1/models 结尾
    if base_url.endswith("/v1"):
        models_url = base_url + "/models"
    elif "/v1/" in base_url:
        # 已经有 /v1/ 后缀（含 path）
        models_url = base_url.rstrip("/") + "/models"
    else:
        models_url = base_url + "/v1/models"

    static_fallback = provider_meta.supported_models or ([provider_meta.default_model] if provider_meta.default_model else [])

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                models_url,
                headers={
                    "Authorization": f"Bearer {payload.api_key}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code != 200:
            logger.warning("fetch-models: %s %s returned %s", payload.provider_name, models_url, resp.status_code)
            return SystemLLMFetchModelsResponse(
                provider_name=payload.provider_name,
                models=static_fallback,
                source="fallback",
                raw_count=0,
                static_fallback=static_fallback,
            )

        data = resp.json()
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list) or len(items) == 0:
            return SystemLLMFetchModelsResponse(
                provider_name=payload.provider_name,
                models=static_fallback,
                source="fallback",
                raw_count=0,
                static_fallback=static_fallback,
            )

        # 提取 id（OpenAI 标准字段）；兼容部分厂商用 name/model 字段
        ids: List[str] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            mid = it.get("id") or it.get("name") or it.get("model")
            if isinstance(mid, str) and mid.strip():
                ids.append(mid.strip())
        # 去重保序
        seen = set()
        unique = []
        for x in ids:
            if x not in seen:
                seen.add(x)
                unique.append(x)
        if not unique:
            return SystemLLMFetchModelsResponse(
                provider_name=payload.provider_name,
                models=static_fallback,
                source="fallback",
                raw_count=len(items),
                static_fallback=static_fallback,
            )
        # 实时成功 → 合并静态列表后写入本地周级缓存，供后续直接命中
        merged = list(unique)
        mseen = set(unique)
        for m in static_fallback:
            if m not in mseen:
                merged.append(m)
                mseen.add(m)
        cache_provider_result(payload.provider_name, merged, "live", len(items))
        return SystemLLMFetchModelsResponse(
            provider_name=payload.provider_name,
            models=merged,
            source="live",
            raw_count=len(items),
            static_fallback=static_fallback,
        )
    except httpx.TimeoutException:
        logger.warning("fetch-models: %s timeout", payload.provider_name)
        return SystemLLMFetchModelsResponse(
            provider_name=payload.provider_name,
            models=static_fallback,
            source="fallback",
            raw_count=0,
            static_fallback=static_fallback,
        )
    except Exception as e:
        logger.warning("fetch-models: %s error: %s", payload.provider_name, str(e)[:200])
        return SystemLLMFetchModelsResponse(
            provider_name=payload.provider_name,
            models=static_fallback,
            source="fallback",
            raw_count=0,
            static_fallback=static_fallback,
        )


@router.post("/llm-config/refresh-model-catalog", response_model=dict)
async def refresh_model_catalog(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_superuser),
):
    """
    立即刷新全部厂商的模型目录缓存（周级后台任务也会自动执行）。
    - 已配置密钥且兼容 OpenAI 协议的厂商走实时 /v1/models；
    - 其余厂商写入 PROVIDER_METADATA 静态列表。
    返回各厂商刷新来源（live / static）汇总。
    """
    try:
        summary = await refresh_all(db)
        return {
            "success": True,
            "message": "模型目录已刷新",
            "updated_at": summary.get("updated_at"),
            "total": summary.get("total"),
            "providers": summary.get("providers"),
        }
    except Exception as e:  # noqa: BLE001
        logger.exception("refresh-model-catalog 失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"刷新模型目录失败：{str(e)}",
        )


async def _load_config(db: AsyncSession) -> SystemLLMConfig | None:
    result = await db.execute(select(SystemLLMConfig).order_by(SystemLLMConfig.updated_at.desc()))
    return result.scalars().first()

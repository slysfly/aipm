"""
PMI中国AI项目管理社区 — 模型目录缓存服务

目标：
- 为每个大模型厂商维护一份「最新在售模型清单」缓存（backend/data/model_catalog.json）。
- 缓存 = 厂商实时 /v1/models 拉取结果（若有密钥且兼容 OpenAI 协议）与 PROVIDER_METADATA
  静态列表的合并（实时优先，静态兜底）。
- 由 lifespan 中的周级后台循环（_model_catalog_loop）定期刷新，管理员也可在前端点
  「立即刷新模型目录」手动触发。
- fetch-models 端点优先读缓存，避免每次打开设置都打厂商 API（节省额度、避免限流）。
"""

import json
import os
import time
import logging
from typing import List, Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

# backend/data/model_catalog.json
_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"
)
CATALOG_PATH = os.path.join(_DATA_DIR, "model_catalog.json")
# 缓存有效期：7 天（与周级刷新对齐，留 1 天余量）
CATALOG_TTL_SECONDS = 7 * 24 * 3600

_catalog: Dict[str, Any] = {}
_loaded = False


def _ensure_dir() -> None:
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
    except Exception:
        pass


def _load() -> None:
    global _catalog, _loaded
    if _loaded:
        return
    if os.path.exists(CATALOG_PATH):
        try:
            with open(CATALOG_PATH, "r", encoding="utf-8") as f:
                _catalog = json.load(f) or {}
        except Exception as e:  # noqa: BLE001
            logger.warning("model_catalog 读取失败，重置为空: %s", e)
            _catalog = {}
    _loaded = True


def _save() -> None:
    _ensure_dir()
    try:
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(_catalog, f, ensure_ascii=False, indent=2)
    except Exception as e:  # noqa: BLE001
        logger.warning("model_catalog 写入失败: %s", e)


def _merge(live: List[str], static: List[str]) -> List[str]:
    """实时列表优先，静态列表中不在实时里的补在后面（去重保序）。"""
    if live:
        merged = list(live)
        seen = set(live)
        for m in static:
            if m not in seen:
                merged.append(m)
                seen.add(m)
        return merged
    return list(static)


def get_provider_entry(provider_name: str) -> Optional[Dict[str, Any]]:
    _load()
    return _catalog.get(provider_name)


def is_fresh(provider_name: str, ttl: int = CATALOG_TTL_SECONDS) -> bool:
    e = get_provider_entry(provider_name)
    if not e:
        return False
    return (time.time() - float(e.get("updated_at", 0))) < ttl


def get_merged_models(
    provider_name: str, static_models: List[str], default_model: Optional[str]
) -> List[str]:
    base = list(static_models) if static_models else ([default_model] if default_model else [])
    e = get_provider_entry(provider_name)
    if not e:
        return base
    return _merge(e.get("models", []), base)


def _build_models_url(base_url: str) -> str:
    base_url = (base_url or "").rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/v1"):
        return base_url + "/models"
    if "/v1/" in base_url:
        return base_url.rstrip("/") + "/models"
    return base_url + "/v1/models"


def _write_entry(
    provider_name: str,
    models: List[str],
    source: str,
    raw_count: int,
) -> Dict[str, Any]:
    _load()
    entry = {
        "provider_name": provider_name,
        "models": models,
        "source": source,
        "raw_count": raw_count,
        "updated_at": time.time(),
    }
    _catalog[provider_name] = entry
    _save()
    return entry


def cache_provider_result(
    provider_name: str, models: List[str], source: str, raw_count: int
) -> Dict[str, Any]:
    """公开封装：把一次实时/合并结果写入缓存（供 fetch-models 实时成功时调用）。"""
    return _write_entry(provider_name, models, source, raw_count)


async def refresh_provider(
    provider_name: str,
    api_key: str,
    base_url: str,
    static_models: List[str],
    default_model: Optional[str],
) -> Dict[str, Any]:
    """实时拉取单个厂商模型并合并静态列表写入缓存。无密钥或不兼容则仅写静态。"""
    models_url = _build_models_url(base_url)
    live: List[str] = []
    source = "static"
    raw_count = 0
    if api_key and models_url:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    models_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data") if isinstance(data, dict) else None
                if isinstance(items, list):
                    raw_count = len(items)
                    seen: set = set()
                    for it in items:
                        if not isinstance(it, dict):
                            continue
                        mid = it.get("id") or it.get("name") or it.get("model")
                        if isinstance(mid, str) and mid.strip() and mid.strip() not in seen:
                            seen.add(mid.strip())
                            live.append(mid.strip())
                    if live:
                        source = "live"
        except Exception as e:  # noqa: BLE001
            logger.warning("model_catalog refresh %s 失败: %s", provider_name, str(e)[:200])

    base = list(static_models) if static_models else ([default_model] if default_model else [])
    models = _merge(live, base)
    return _write_entry(provider_name, models, source, raw_count)


async def refresh_all(db) -> Dict[str, Any]:
    """对所有厂商刷新模型目录：有密钥且兼容 /v1/models 的走实时，其余静态兜底。"""
    from app.api.v1.llm_configs import PROVIDER_METADATA
    from app.models.system_llm_config import SystemLLMConfig
    from app.models.llm_config import LLMConfig
    from sqlalchemy import select

    # 收集可用密钥：优先系统默认配置，其次用户已启用配置
    key_by_provider: Dict[str, str] = {}
    try:
        res = await db.execute(select(SystemLLMConfig))
        syscfg = res.scalars().first()
        if syscfg and syscfg.api_key:
            key_by_provider[syscfg.provider_name] = syscfg.api_key
    except Exception as e:  # noqa: BLE001
        logger.warning("读取系统大模型配置失败: %s", e)
    try:
        res = await db.execute(select(LLMConfig).where(LLMConfig.is_enabled == True))  # noqa: E712
        for c in res.scalars().all():
            if c.api_key and c.provider_name not in key_by_provider:
                key_by_provider[c.provider_name] = c.api_key
    except Exception as e:  # noqa: BLE001
        logger.warning("读取用户大模型配置失败: %s", e)

    results: Dict[str, str] = {}
    for name, meta in PROVIDER_METADATA.items():
        if meta.supports_models_endpoint and name in key_by_provider:
            entry = await refresh_provider(
                name,
                key_by_provider[name],
                meta.default_base_url,
                list(meta.supported_models),
                meta.default_model,
            )
        else:
            base = (
                list(meta.supported_models)
                if meta.supported_models
                else ([meta.default_model] if meta.default_model else [])
            )
            entry = _write_entry(name, base, "static", 0)
        results[name] = entry.get("source")

    return {"updated_at": time.time(), "providers": results, "total": len(results)}

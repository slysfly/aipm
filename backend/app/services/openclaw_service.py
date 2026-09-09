"""
PMI中国AI项目管理社区 - OpenClaw 适配层
目标：让本地安装的 OpenClaw 始终使用与本系统一致的大模型配置。

工作机制：
1) 本系统大模型配置变更时，将配置写入 OpenClaw 本地配置文件（~/.openclaw/system_model.json），
   OpenClaw 安装/启动后读取即可即插即用（无需手动再配一次）。
2) 若 OpenClaw 服务正在运行（配置的 base_url，默认 http://localhost:18888），同时向其 HTTP 接口推送同步。
3) 接入地址与开关已持久化到数据库（openclaw_configs 表），替代原有全局变量。
"""

import os
import json
import logging
import httpx
from typing import Optional, Dict, Any

from app.db.session import async_session_maker
from app.models import OpenClawConfig
from sqlalchemy import select

logger = logging.getLogger("app.openclaw")

OPENCLAW_CONFIG_PATH = os.path.expanduser("~/.openclaw/system_model.json")


async def _get_or_create_config() -> OpenClawConfig:
    """获取当前生效的 OpenClaw 配置；若不存在则创建默认记录并返回。"""
    async with async_session_maker() as db:
        result = await db.execute(select(OpenClawConfig).limit(1))
        cfg = result.scalar_one_or_none()
        if cfg is not None:
            return cfg
        cfg = OpenClawConfig(
            base_url="http://localhost:18888",
            enabled=True,
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
        logger.info("已创建默认 OpenClaw 配置记录 (base_url=%s, enabled=True)", cfg.base_url)
        return cfg


async def get_openclaw_config() -> OpenClawConfig:
    """获取当前 OpenClaw 配置（始终有返回值，首次调用自动创建默认配置）。"""
    return await _get_or_create_config()


async def configure_openclaw(base_url: str, enabled: bool) -> OpenClawConfig:
    """更新 OpenClaw 接入配置。"""
    async with async_session_maker() as db:
        result = await db.execute(select(OpenClawConfig).limit(1))
        cfg = result.scalar_one_or_none()
        if cfg is None:
            cfg = OpenClawConfig(base_url=base_url, enabled=enabled)
            db.add(cfg)
        else:
            cfg.base_url = base_url
            cfg.enabled = enabled
        await db.commit()
        await db.refresh(cfg)
        logger.info("OpenClaw 配置已更新: base_url=%s, enabled=%s", base_url, enabled)
        return cfg


async def sync_model_to_openclaw(
    provider_name: str,
    api_key: str,
    base_url: Optional[str],
    model_name: str,
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any]:
    """将本系统的大模型配置同步给 OpenClaw。

    返回统一结果字典。即使 OpenClaw 未安装也不会报错（写入本地文件即可）。
    """
    payload: Dict[str, Any] = {
        "provider": provider_name,
        "api_key": api_key,
        "base_url": base_url,
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "synced_by": "ai-pm-system",
    }

    # 1) 始终写入本地配置文件（OpenClaw 安装后读取即可即插即用）
    local_ok = False
    try:
        os.makedirs(os.path.dirname(OPENCLAW_CONFIG_PATH), exist_ok=True)
        with open(OPENCLAW_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        local_ok = True
        logger.info("已写入 OpenClaw 本地配置: %s", OPENCLAW_CONFIG_PATH)
    except Exception as e:  # pragma: no cover
        logger.warning("写入 OpenClaw 本地配置失败: %s", e)

    # 2) 若 OpenClaw 服务可达，推送 HTTP 同步（未安装则忽略）
    http_ok = False
    detail: Dict[str, Any] = {}
    try:
        oc_cfg = await _get_or_create_config()
        if oc_cfg.enabled:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(f"{oc_cfg.base_url}/v1/model/sync", json=payload)
                http_ok = r.status_code < 400
                detail = {"http_status": r.status_code}
    except Exception as e:
        detail = {"http_error": str(e)}

    success = local_ok or http_ok
    if http_ok:
        msg = "已向 OpenClaw 推送大模型配置同步"
    elif local_ok:
        msg = "已写入 OpenClaw 本地配置（OpenClaw 未运行，启动后将自动加载）"
    else:
        msg = "OpenClaw 同步失败：本地写入与服务推送均失败"
    return {"success": success, "message": msg, "detail": detail}

"""
PMI中国AI项目管理社区 - 对外 API（外部对接）启用配置

以 JSON 文件持久化（与品牌 Logo 同目录 backend/static/uploads），
记录管理员是否在「系统设置 > 外部对接」中开放了对 API 端口。
默认值：未启用（enabled=False），即 /external/* 全部返回 403。
"""

import json
from datetime import datetime
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # .../backend/
_CONFIG_DIR = _BACKEND_DIR / "static" / "uploads"
_CONFIG_FILE = _CONFIG_DIR / "external_api_config.json"

DEFAULT_CONFIG: dict = {
    "enabled": False,
    "public_base_url": "",
    "note": "",
    "updated_at": None,
    "updated_by": None,
}


def load_config() -> dict:
    """读取对外 API 启用配置；文件不存在或损坏时返回默认值。"""
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text("utf-8"))
            merged = dict(DEFAULT_CONFIG)
            merged.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
            return merged
        except Exception:
            return dict(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(
    enabled: bool,
    public_base_url: str = "",
    note: str = "",
    updated_by: str = None,
) -> dict:
    """保存对外 API 启用配置，返回最新配置。"""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "enabled": bool(enabled),
        "public_base_url": (public_base_url or "").strip(),
        "note": (note or "").strip(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "updated_by": updated_by,
    }
    _CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    return data


def is_enabled() -> bool:
    """对外 API 是否处于开放状态（供 external.router 总闸使用）。"""
    return bool(load_config().get("enabled"))

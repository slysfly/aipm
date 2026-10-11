"""
统一运行时路径解析（Issue #4：硬编码服务器绝对路径收口）

背景
----
业务代码曾把服务器安装根目录（A 机与 B 机各有一套不同的写法）以字面量写死在
十余个模块里，两套部署的写法还互不一致。把系统自部署到其它目录时，这些数据
文件全部读不到，而失败方式是「只打一条 warning 然后返回」——最典型的表现就是
Agent 注册表静默为空（不报错、不崩溃，只是结果为空）。

约定
----
本模块是运行时数据路径的唯一解析入口。业务代码只能通过 data_path() / DATA_DIR /
BACKEND_DIR / DB_FILE 取得路径，不得再出现任何字面量安装路径。

解析优先级（以 DATA_DIR 为例）
-----------------------------
  1) 环境变量 AIPM_DATA_DIR         —— 显式覆盖，供自部署 / 容器化使用
  2) settings.DATA_DIR               —— 支持写进 .env（由 app.config 提供）
  3) 默认值：由本文件位置推导        —— <backend>/data

     * A 机推导为「A 机安装根/backend/data」
     * B 机推导为「B 机安装根/backend/data」

     与改动前各机器上的字面量完全一致，因此**不配置任何环境变量时行为零变化**。

环境变量
--------
  AIPM_DATA_DIR     运行时数据目录（默认 <backend>/data）
  AIPM_DB_FILE      SQLite 库文件路径（默认 <backend>/production.db）
  AIPM_BACKEND_DIR  backend 目录（默认由本文件位置推导）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

__all__ = [
    "BACKEND_DIR",
    "DATA_DIR",
    "DB_FILE",
    "data_path",
    "backend_path",
]


def _derive_backend_dir() -> Path:
    """由本文件位置推导 backend 目录：app/paths.py -> parents[1] = <backend>。"""
    return Path(__file__).resolve().parents[1]


# 安装根目录（backend 目录）。可用 AIPM_BACKEND_DIR 覆盖。
BACKEND_DIR: Path = Path(os.environ.get("AIPM_BACKEND_DIR", "").strip() or _derive_backend_dir())

_DEFAULT_DATA_DIR: Path = BACKEND_DIR / "data"
_DEFAULT_DB_FILE: Path = BACKEND_DIR / "production.db"


def _from_settings(attr: str) -> str:
    """尝试从 app.config 的 settings 读取同名覆盖项（从而支持 .env）。

    本模块必须能在最小依赖下独立导入，因此这里吞掉一切异常：
    读不到就返回空串，回退到推导出的默认值。
    """
    try:
        from app.config import settings  # 延迟导入，避免循环依赖

        value = getattr(settings, attr, "")
        return str(value).strip() if value else ""
    except Exception:
        return ""


def _resolve(env_name: str, settings_attr: str, default: Path) -> Path:
    """按 环境变量 -> settings(.env) -> 推导默认值 的优先级解析路径。"""
    raw = os.environ.get(env_name, "").strip()
    if raw:
        return Path(raw).expanduser()
    raw = _from_settings(settings_attr)
    if raw:
        return Path(raw).expanduser()
    return default


DATA_DIR: Path = _resolve("AIPM_DATA_DIR", "DATA_DIR", _DEFAULT_DATA_DIR)

DB_FILE: Path = _resolve("AIPM_DB_FILE", "DB_FILE", _DEFAULT_DB_FILE)


def data_path(*parts: Union[str, os.PathLike]) -> Path:
    """返回 DATA_DIR 下的路径。

    例：data_path('pmbok_v3', 'agents.json') -> <DATA_DIR>/pmbok_v3/agents.json
    """
    return DATA_DIR.joinpath(*parts)


def backend_path(*parts: Union[str, os.PathLike]) -> Path:
    """返回 BACKEND_DIR 下的路径。"""
    return BACKEND_DIR.joinpath(*parts)

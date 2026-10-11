"""
LLM HTTP 连接池。

背景（性能问题）：原先每个 Provider 的每次调用都写
    async with httpx.AsyncClient(timeout=...) as client:
即「一次调用 = 一次全新的 DNS 解析 + TCP 三次握手 + TLS 握手」，且连接用完即关，
无法复用 HTTP/1.1 keep-alive。跨境访问大模型 API 时这一项就固定吃掉
200~600ms，是「AI 帮我填」端到端延迟里最不该存在的一段。

本模块提供进程级共享的 AsyncClient：
- 按事件循环缓存（避免跨 loop 复用导致 "attached to a different loop"）；
- 同一事件循环内按 timeout 组合缓存，连接池跨请求复用；
- 通过 `shared_client()` 返回一个「退出时不关闭底层连接」的代理，
  因此各 Provider 只需把 `httpx.AsyncClient(...)` 换成 `shared_client(...)`，
  不必改动任何缩进与业务逻辑。

用法：
    from app.core.ai_engine.http_pool import shared_client

    async with shared_client(20.0) as client:      # 复用共享连接，退出不关闭
        resp = await client.post(url, headers=..., json=...)

    async with shared_client(read=60.0, connect=5.0) as client:   # 也可分项指定
        ...
"""
from __future__ import annotations

import asyncio
import logging
import weakref
from typing import Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# 连接池上限：并发调用大模型时复用长连接，避免每次重开
_LIMITS = httpx.Limits(
    max_connections=64,
    max_keepalive_connections=32,
    keepalive_expiry=90.0,
)

# loop -> {(connect, read, write, pool): AsyncClient}
_pool: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Dict[Tuple[float, float, float, float], httpx.AsyncClient]]" = (
    weakref.WeakKeyDictionary()
)


def _build_timeout(
    scalar: Optional[float],
    connect: Optional[float],
    read: Optional[float],
    write: Optional[float],
    pool: Optional[float],
) -> httpx.Timeout:
    """兼容旧写法：传入单个标量时，等价于 httpx.AsyncClient(timeout=标量)，
    但把 connect/write/pool 收紧，使「连不上」快速失败而不是干等整个 read 预算。"""
    if scalar is not None:
        base = float(scalar)
        return httpx.Timeout(
            connect=min(base, 10.0),
            read=base,
            write=min(base, 15.0),
            pool=min(base, 5.0),
        )
    return httpx.Timeout(
        connect=connect if connect is not None else 10.0,
        read=read if read is not None else 60.0,
        write=write if write is not None else 15.0,
        pool=pool if pool is not None else 5.0,
    )


def get_shared_client(
    scalar_timeout: Optional[float] = None,
    *,
    connect: Optional[float] = None,
    read: Optional[float] = None,
    write: Optional[float] = None,
    pool: Optional[float] = None,
) -> httpx.AsyncClient:
    """取（或创建）当前事件循环下、指定超时组合的共享 AsyncClient。"""
    loop = asyncio.get_running_loop()
    timeout = _build_timeout(scalar_timeout, connect, read, write, pool)
    key = (timeout.connect, timeout.read, timeout.write, timeout.pool)

    per_loop = _pool.get(loop)
    if per_loop is None:
        per_loop = {}
        _pool[loop] = per_loop

    client = per_loop.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=timeout, limits=_LIMITS)
        per_loop[key] = client
        logger.debug("创建共享 LLM HTTP 客户端 timeout=%s", key)
    return client


class _SharedClientHandle:
    """`async with shared_client(...) as client:` 的代理。

    __aexit__ 故意不关闭底层客户端 —— 连接要留给后续请求复用。
    """

    __slots__ = ("_client",)

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: D105
        return False


def shared_client(scalar_timeout: Optional[float] = None, **kwargs) -> _SharedClientHandle:
    """`httpx.AsyncClient(timeout=...)` 的即插即用替代品（复用连接）。"""
    return _SharedClientHandle(get_shared_client(scalar_timeout, **kwargs))


async def aclose_all() -> None:
    """应用关闭时释放所有共享连接。"""
    for per_loop in list(_pool.values()):
        for client in list(per_loop.values()):
            try:
                await client.aclose()
            except Exception:
                pass
        per_loop.clear()
    logger.debug("共享 LLM HTTP 连接池已释放")

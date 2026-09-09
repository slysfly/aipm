"""
PMI中国AI项目管理社区 - 外部集成公共辅助
提供真实的 OAuth2 授权码换取、真实的 API GET 调用，以及 mock 凭证守卫，
确保未配置真实凭证时绝不返回假数据。
"""

import httpx
from typing import Optional, Dict, Any, List

from app.core.exceptions import BusinessException


MOCK_PREFIXES = ("mock_", "gho_", "test_", "fake_")


def is_mock(value) -> bool:
    """判断值是否为占位/未配置凭证"""
    if not value:
        return True
    s = str(value)
    return any(s.startswith(p) for p in MOCK_PREFIXES)


async def exchange_oauth_code(
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """真实换取 OAuth2 访问令牌"""
    if is_mock(client_id) or is_mock(client_secret):
        raise BusinessException("集成未配置真实凭证（请在 settings 配置 CLIENT_ID/CLIENT_SECRET）")

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    if extra:
        data.update(extra)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(token_url, data=data)
    except Exception as e:
        raise BusinessException(f"换取 token 请求失败: {e}")

    if resp.status_code >= 400:
        raise BusinessException(f"换取 token 失败（HTTP {resp.status_code}）: {resp.text[:500]}")

    try:
        result = resp.json()
    except Exception:
        raise BusinessException(f"平台返回了非 JSON 响应: {resp.text[:500]}")

    if "error" in result and "access_token" not in result:
        raise BusinessException(f"换取 token 失败: {result.get('error_description') or result['error']}")

    if not result.get("access_token"):
        raise BusinessException("平台未返回 access_token")

    return result


async def api_get(
    url: str,
    token: str,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    """真实调用平台 API（GET），返回解析后的 JSON"""
    if is_mock(token):
        raise BusinessException("请先完成 OAuth 授权获取真实访问令牌")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers, params=params)
    except Exception as e:
        raise BusinessException(f"调用接口失败: {e}")

    if resp.status_code >= 400:
        raise BusinessException(f"接口请求失败（HTTP {resp.status_code}）: {resp.text[:500]}")

    try:
        return resp.json()
    except Exception:
        raise BusinessException(f"接口返回了非 JSON 响应: {resp.text[:500]}")


async def api_post(
    url: str,
    token: str = "",
    json: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    """真实调用平台 API（POST），返回解析后的 JSON"""
    if is_mock(token):
        raise BusinessException("请先完成 OAuth 授权获取真实访问令牌")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=json, data=data, params=params, headers=headers)
    except Exception as e:
        raise BusinessException(f"调用接口失败: {e}")

    if resp.status_code >= 400:
        raise BusinessException(f"接口请求失败（HTTP {resp.status_code}）: {resp.text[:500]}")

    try:
        return resp.json()
    except Exception:
        raise BusinessException(f"接口返回了非 JSON 响应: {resp.text[:500]}")


def require_real(*values) -> None:
    """
    真实凭证守卫：任一值为占位/未配置则明确报错（绝不返回假数据）。
    真实凭证场景下安静通过，由调用方发起真实 API 请求。
    """
    if any(is_mock(v) for v in values if v is not None):
        raise BusinessException("集成未配置真实凭证，无法返回真实数据")

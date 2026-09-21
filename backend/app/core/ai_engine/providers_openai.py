import json
from typing import AsyncIterator, Dict, Any, List, Optional

import httpx

from app.config import settings
from app.core.ai_engine.base import LLMProvider
from app.core.ai_engine.http_pool import shared_client
import logging

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.base_url = base_url or "https://api.openai.com/v1"
        self.model = model or settings.LLM_MODEL
        self.default_temperature = settings.LLM_TEMPERATURE
        self.default_max_tokens = settings.LLM_MAX_TOKENS
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "OpenAI API key not configured. Please set OPENAI_API_KEY in your .env file."
        return True, ""

    async def generate(self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, temperature, max_tokens)

    async def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        is_available, error_msg = self.check_config()
        if not is_available:
            raise RuntimeError(error_msg)

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
        }

        async with shared_client(120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def stream_chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> AsyncIterator[str]:
        is_available, error_msg = self.check_config()
        if not is_available:
            raise RuntimeError(error_msg)

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
            "stream": True,
        }

        async with shared_client(120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue


class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self.base_url = base_url or "https://api.deepseek.com/v1"
        self.model = model or "deepseek-chat"
        self.default_temperature = settings.LLM_TEMPERATURE
        self.default_max_tokens = settings.LLM_MAX_TOKENS
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "DeepSeek API key not configured. Please set DEEPSEEK_API_KEY in your .env file."
        return True, ""

    async def generate(self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, temperature, max_tokens)

    async def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        is_available, error_msg = self.check_config()
        if not is_available:
            raise RuntimeError(error_msg)

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
        }

        async with shared_client(120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def stream_chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> AsyncIterator[str]:
        is_available, error_msg = self.check_config()
        if not is_available:
            raise RuntimeError(error_msg)

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
            "stream": True,
        }

        async with shared_client(120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue


class AnthropicProvider(LLMProvider):
    """Anthropic Claude Provider"""
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.base_url = base_url or "https://api.anthropic.com/v1"
        self.model = model or "claude-3-5-sonnet-20241022"
        self.default_temperature = settings.LLM_TEMPERATURE
        self.default_max_tokens = settings.LLM_MAX_TOKENS
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "Anthropic API key not configured. Please set ANTHROPIC_API_KEY in your .env file."
        return True, ""

    def _convert_messages(self, messages: List[Dict[str, str]]) -> tuple:
        """将标准消息格式转换为Anthropic格式"""
        system = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append({"role": msg["role"], "content": msg["content"]})
        return system, chat_messages

    async def generate(self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, temperature, max_tokens)

    async def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        is_available, error_msg = self.check_config()
        if not is_available:
            raise RuntimeError(error_msg)

        system, chat_messages = self._convert_messages(messages)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": max_tokens or self.default_max_tokens,
        }
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature

        async with shared_client(120.0) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]

    async def stream_chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> AsyncIterator[str]:
        is_available, error_msg = self.check_config()
        if not is_available:
            raise RuntimeError(error_msg)

        system, chat_messages = self._convert_messages(messages)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": max_tokens or self.default_max_tokens,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature

        async with shared_client(120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/messages",
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        try:
                            data = json.loads(data_str)
                            if data.get("type") == "content_block_delta":
                                delta = data.get("delta", {})
                                text = delta.get("text", "")
                                if text:
                                    yield text
                        except (json.JSONDecodeError, KeyError):
                            continue


class OpenAICompatibleProvider(LLMProvider):
    """通用兼容OpenAI API格式的Provider"""
    supports_json_mode = True

    def __init__(self, api_key: str, base_url: str, model: str, temperature: float = 0.7, max_tokens: int = 2000):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.default_temperature = temperature
        self.default_max_tokens = max_tokens
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # 该网关是否接受 response_format=json_object。首次被拒后自动降级并记住，
        # 避免不支持的网关每次请求都白跑一趟。
        self._json_mode_supported = True

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "API key not configured."
        if not self.base_url or not self.base_url.strip():
            return False, "Base URL not configured. Please set OPENAI_COMPATIBLE_BASE_URL in your .env file."
        if not self.model or not self.model.strip():
            return False, "Model name not configured."
        return True, ""

    async def generate(self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None, json_mode: bool = False) -> str:
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, temperature, max_tokens, json_mode=json_mode)

    @staticmethod
    def _extract_content(data: Dict[str, Any]) -> str:
        """取正文。部分推理型模型把内容放在 reasoning_content 里而 content 为空；
        原来直接取 ["content"] 会因 None/缺键让调用方拿到空串或直接抛 KeyError。"""
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            return ""
        text = msg.get("content")
        if not text:
            text = msg.get("reasoning_content") or ""
        return text or ""

    async def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None, json_mode: bool = False) -> str:
        is_available, error_msg = self.check_config()
        if not is_available:
            raise RuntimeError(error_msg)

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
        }
        # JSON 模式：让网关保证输出是合法 JSON，省掉截断 / markdown 围栏 / 解释文字的修复成本
        use_json_mode = bool(json_mode) and self._json_mode_supported
        if use_json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with shared_client(120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            )
            # 不支持 response_format 的网关通常回 400/415/422 —— 去掉后重试一次，并记住
            if use_json_mode and response.status_code in (400, 404, 415, 422):
                self._json_mode_supported = False
                logger.warning(
                    "网关不支持 response_format=json_object（HTTP %s），本次降级为普通模式并记住",
                    response.status_code,
                )
                payload.pop("response_format", None)
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload,
                )
            response.raise_for_status()
            data = response.json()
            return self._extract_content(data)

    async def stream_chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> AsyncIterator[str]:
        is_available, error_msg = self.check_config()
        if not is_available:
            raise RuntimeError(error_msg)

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
            "stream": True,
        }

        async with shared_client(120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue

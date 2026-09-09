import json
from typing import AsyncIterator, Dict, Any, List, Optional

import httpx

from app.config import settings
from app.core.ai_engine.base import LLMProvider
from app.core.ai_engine.providers_openai import OpenAIProvider
import logging

logger = logging.getLogger(__name__)


class BaiduProvider(LLMProvider):
    """百度文心一言 Provider"""
    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.BAIDU_API_KEY
        self.secret_key = secret_key or settings.BAIDU_SECRET_KEY
        self.base_url = base_url or "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"
        self.model = model or "ernie-bot-4"
        self.default_temperature = settings.LLM_TEMPERATURE
        self.default_max_tokens = settings.LLM_MAX_TOKENS
        self._access_token: Optional[str] = None

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "Baidu API key not configured. Please set BAIDU_API_KEY in your .env file."
        if not self.secret_key or not self.secret_key.strip():
            return False, "Baidu secret key not configured. Please set BAIDU_SECRET_KEY in your .env file."
        return True, ""

    async def _get_access_token(self) -> str:
        """获取百度access_token"""
        if self._access_token:
            return self._access_token
        if not self.api_key or not self.secret_key:
            raise RuntimeError("Baidu API key or secret key not configured")

        url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={self.api_key}&client_secret={self.secret_key}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url)
            response.raise_for_status()
            data = response.json()
            self._access_token = data["access_token"]
            return self._access_token

    async def generate(self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, temperature, max_tokens)

    async def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        access_token = await self._get_access_token()

        payload = {
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_output_tokens": max_tokens or self.default_max_tokens,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.base_url}/{self.model}?access_token={access_token}",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            if "error_code" in data:
                raise RuntimeError(f"Baidu API error: {data.get('error_msg', 'Unknown error')}")
            return data["result"]

    async def stream_chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> AsyncIterator[str]:
        access_token = await self._get_access_token()

        payload = {
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_output_tokens": max_tokens or self.default_max_tokens,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/{self.model}?access_token={access_token}",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "error_code" in data:
                            raise RuntimeError(f"Baidu API error: {data.get('error_msg', 'Unknown error')}")
                        result = data.get("result", "")
                        if result:
                            yield result
                    except (json.JSONDecodeError, KeyError):
                        continue


class AliyunProvider(LLMProvider):
    """阿里通义千问 Provider"""
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.ALIYUN_API_KEY
        self.base_url = base_url or "https://dashscope.aliyuncs.com/api/v1"
        self.model = model or "qwen-max"
        self.default_temperature = settings.LLM_TEMPERATURE
        self.default_max_tokens = settings.LLM_MAX_TOKENS
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "Aliyun API key not configured. Please set ALIYUN_API_KEY in your .env file."
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
            "input": {"messages": messages},
            "parameters": {
                "temperature": temperature or self.default_temperature,
                "max_tokens": max_tokens or self.default_max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.base_url}/services/aigc/text-generation/generation",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            if "output" in data and "text" in data["output"]:
                return data["output"]["text"]
            return data.get("output", {}).get("choices", [{}])[0].get("message", {}).get("content", "")

    async def stream_chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> AsyncIterator[str]:
        is_available, error_msg = self.check_config()
        if not is_available:
            raise RuntimeError(error_msg)

        payload = {
            "model": self.model,
            "input": {"messages": messages},
            "parameters": {
                "temperature": temperature or self.default_temperature,
                "max_tokens": max_tokens or self.default_max_tokens,
                "incremental_output": True,
            },
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/services/aigc/text-generation/generation",
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "output" in data and "text" in data["output"]:
                            yield data["output"]["text"]
                        elif "output" in data and "choices" in data["output"]:
                            text = data["output"]["choices"][0].get("message", {}).get("content", "")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


class TencentProvider(LLMProvider):
    """腾讯混元 Provider"""
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.TENCENT_API_KEY
        self.base_url = base_url or "https://hunyuan.tencentcloudapi.com/v1"
        self.model = model or "hunyuan-pro"
        self.default_temperature = settings.LLM_TEMPERATURE
        self.default_max_tokens = settings.LLM_MAX_TOKENS
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "Tencent API key not configured. Please set TENCENT_API_KEY in your .env file."
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

        async with httpx.AsyncClient(timeout=20.0) as client:
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

        async with httpx.AsyncClient(timeout=20.0) as client:
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


class ZhipuProvider(LLMProvider):
    """智谱GLM Provider"""
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.ZHIPU_API_KEY
        self.base_url = base_url or "https://open.bigmodel.cn/api/paas/v4"
        self.model = model or "glm-4"
        self.default_temperature = settings.LLM_TEMPERATURE
        self.default_max_tokens = settings.LLM_MAX_TOKENS
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "Zhipu API key not configured. Please set ZHIPU_API_KEY in your .env file."
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

        async with httpx.AsyncClient(timeout=20.0) as client:
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

        async with httpx.AsyncClient(timeout=20.0) as client:
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


class MoonshotProvider(LLMProvider):
    """Moonshot Kimi Provider"""
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.MOONSHOT_API_KEY
        self.base_url = base_url or "https://api.moonshot.cn/v1"
        self.model = model or "moonshot-v1-8k"
        self.default_temperature = settings.LLM_TEMPERATURE
        self.default_max_tokens = settings.LLM_MAX_TOKENS
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "Moonshot API key not configured. Please set MOONSHOT_API_KEY in your .env file."
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

        async with httpx.AsyncClient(timeout=20.0) as client:
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

        async with httpx.AsyncClient(timeout=20.0) as client:
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


class QwenProvider(LLMProvider):
    """通义千问 Provider"""
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.QWEN_API_KEY
        self.base_url = base_url or "https://dashscope.aliyuncs.com/api/v1"
        self.model = model or "qwen-max"
        self.default_temperature = settings.LLM_TEMPERATURE
        self.default_max_tokens = settings.LLM_MAX_TOKENS
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "Qwen API key not configured. Please set QWEN_API_KEY in your .env file."
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
            "input": {"messages": messages},
            "parameters": {
                "temperature": temperature or self.default_temperature,
                "max_tokens": max_tokens or self.default_max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.base_url}/services/aigc/text-generation/generation",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            if "output" in data and "text" in data["output"]:
                return data["output"]["text"]
            return data.get("output", {}).get("choices", [{}])[0].get("message", {}).get("content", "")

    async def stream_chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> AsyncIterator[str]:
        is_available, error_msg = self.check_config()
        if not is_available:
            raise RuntimeError(error_msg)

        payload = {
            "model": self.model,
            "input": {"messages": messages},
            "parameters": {
                "temperature": temperature or self.default_temperature,
                "max_tokens": max_tokens or self.default_max_tokens,
                "incremental_output": True,
            },
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/services/aigc/text-generation/generation",
                headers=self.headers,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if "output" in data and "text" in data["output"]:
                            yield data["output"]["text"]
                        elif "output" in data and "choices" in data["output"]:
                            text = data["output"]["choices"][0].get("message", {}).get("content", "")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


class SiliconFlowProvider(LLMProvider):
    """硅基流动 Provider"""
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.SILICONFLOW_API_KEY
        self.base_url = base_url or "https://api.siliconflow.cn/v1"
        self.model = model or "deepseek-ai/DeepSeek-V2.5"
        self.default_temperature = settings.LLM_TEMPERATURE
        self.default_max_tokens = settings.LLM_MAX_TOKENS
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "SiliconFlow API key not configured. Please set SILICONFLOW_API_KEY in your .env file."
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

        async with httpx.AsyncClient(timeout=20.0) as client:
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

        async with httpx.AsyncClient(timeout=20.0) as client:
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


class MiniMaxProvider(OpenAIProvider):
    """MiniMax 大模型 Provider（OpenAI 兼容协议）

    官方 OpenAI 兼容端点：https://api.minimax.chat/v1
    模型：MiniMax-M2.7 / MiniMax-Text-01 / abab6.5-chat 等。
    可选 GroupId 以兼容旧版账号（新版 API Key 免 GroupId）。
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 model: Optional[str] = None, group_id: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 2000):
        self.api_key = api_key or settings.MINIMAX_API_KEY
        self.base_url = (base_url or "https://api.minimax.chat/v1").rstrip("/")
        self.model = model or "MiniMax-M2.7"
        self.default_temperature = temperature
        self.default_max_tokens = max_tokens
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if group_id:
            self.headers["GroupId"] = group_id

    def check_config(self) -> tuple[bool, str]:
        if not self.api_key or not self.api_key.strip():
            return False, "MiniMax API key not configured. Please set MINIMAX_API_KEY or fill it in System LLM Settings."
        return True, ""

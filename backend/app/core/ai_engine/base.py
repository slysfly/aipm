from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, List, Optional


class LLMProvider(ABC):
    # 子类若支持 response_format={"type":"json_object"}，置为 True。
    # 调用方据此决定是否传 json_mode —— 避免对不支持该参数的网关硬传导致 400。
    supports_json_mode: bool = False

    @abstractmethod
    async def generate(self, prompt: str, temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        pass

    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        pass

    @abstractmethod
    async def stream_chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> AsyncIterator[str]:
        pass

    @abstractmethod
    def check_config(self) -> tuple[bool, str]:
        """检查Provider配置是否完整，返回 (是否可用, 错误信息)"""
        pass

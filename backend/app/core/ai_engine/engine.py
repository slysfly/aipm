from typing import AsyncIterator, Dict, Any, List, Optional

import httpx
import time

from app.config import settings
from app.core.ai_engine.base import LLMProvider
from app.core.ai_engine.providers_openai import (
    OpenAIProvider,
    DeepSeekProvider,
    AnthropicProvider,
    OpenAICompatibleProvider,
)
from app.core.ai_engine.providers_china import (
    BaiduProvider,
    AliyunProvider,
    TencentProvider,
    ZhipuProvider,
    MoonshotProvider,
    QwenProvider,
    SiliconFlowProvider,
    MiniMaxProvider,
)
import logging

logger = logging.getLogger(__name__)


class AIEngine:
    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._default_provider_name = "openai"
        self._user_configs: Dict[str, Dict[str, Any]] = {}

    def register_provider(self, name: str, provider: LLMProvider) -> None:
        self._providers[name] = provider

    def get_provider(self, name: Optional[str] = None) -> LLMProvider:
        provider_name = name or self._default_provider_name
        if provider_name not in self._providers:
            if provider_name == "openai":
                self._providers[provider_name] = OpenAIProvider()
            elif provider_name == "deepseek":
                self._providers[provider_name] = DeepSeekProvider()
            elif provider_name == "anthropic":
                self._providers[provider_name] = AnthropicProvider()
            elif provider_name == "baidu":
                self._providers[provider_name] = BaiduProvider()
            elif provider_name == "aliyun":
                self._providers[provider_name] = AliyunProvider()
            elif provider_name == "tencent":
                self._providers[provider_name] = TencentProvider()
            elif provider_name == "zhipu":
                self._providers[provider_name] = ZhipuProvider()
            elif provider_name == "moonshot":
                self._providers[provider_name] = MoonshotProvider()
            elif provider_name == "qwen":
                self._providers[provider_name] = QwenProvider()
            elif provider_name == "siliconflow":
                self._providers[provider_name] = SiliconFlowProvider()
            elif provider_name == "minimax":
                self._providers[provider_name] = MiniMaxProvider()
            else:
                raise ValueError(f"Unknown provider: {provider_name}")
        return self._providers[provider_name]

    def create_provider_from_config(
        self,
        provider_name: str,
        api_key: str,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> LLMProvider:
        """根据用户配置动态创建Provider"""
        if provider_name == "openai":
            return OpenAIProvider(api_key=api_key, base_url=base_url, model=model_name)
        elif provider_name == "deepseek":
            return DeepSeekProvider(api_key=api_key, base_url=base_url, model=model_name)
        elif provider_name == "anthropic":
            return AnthropicProvider(api_key=api_key, base_url=base_url, model=model_name)
        elif provider_name == "baidu":
            return BaiduProvider(api_key=api_key, base_url=base_url, model=model_name)
        elif provider_name == "aliyun":
            return AliyunProvider(api_key=api_key, base_url=base_url, model=model_name)
        elif provider_name == "tencent":
            return TencentProvider(api_key=api_key, base_url=base_url, model=model_name)
        elif provider_name == "zhipu":
            return ZhipuProvider(api_key=api_key, base_url=base_url, model=model_name)
        elif provider_name == "moonshot":
            return MoonshotProvider(api_key=api_key, base_url=base_url, model=model_name)
        elif provider_name == "qwen":
            return QwenProvider(api_key=api_key, base_url=base_url, model=model_name)
        elif provider_name == "siliconflow":
            return SiliconFlowProvider(api_key=api_key, base_url=base_url, model=model_name)
        elif provider_name == "minimax":
            return MiniMaxProvider(
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        elif provider_name == "openai_compatible":
            if not base_url or not model_name:
                raise ValueError("OpenAI compatible provider requires base_url and model_name")
            return OpenAICompatibleProvider(
                api_key=api_key,
                base_url=base_url,
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    def load_user_config(self, user_id: str, config: Dict[str, Any]) -> None:
        """加载用户自定义LLM配置"""
        self._user_configs[user_id] = config
        provider_name = config.get("provider_name")
        if provider_name:
            try:
                provider = self.create_provider_from_config(
                    provider_name=provider_name,
                    api_key=config.get("api_key", ""),
                    base_url=config.get("base_url"),
                    model_name=config.get("model_name"),
                    temperature=config.get("temperature", 0.7),
                    max_tokens=config.get("max_tokens", 2000),
                )
                user_provider_key = f"{user_id}:{provider_name}"
                self._providers[user_provider_key] = provider
            except Exception as e:
                logger.warning("加载用户 LLM 配置失败 (user=%s, provider=%s): %s", user_id, provider_name, e, exc_info=True)

    def get_user_provider(self, user_id: str, provider_name: Optional[str] = None) -> LLMProvider:
        """获取用户配置的Provider，优先使用用户默认配置"""
        user_config = self._user_configs.get(user_id)
        if user_config:
            target_provider = provider_name or user_config.get("provider_name")
            user_provider_key = f"{user_id}:{target_provider}"
            if user_provider_key in self._providers:
                return self._providers[user_provider_key]
            # 如果未缓存，动态创建
            if target_provider:
                return self.create_provider_from_config(
                    provider_name=target_provider,
                    api_key=user_config.get("api_key", ""),
                    base_url=user_config.get("base_url"),
                    model_name=user_config.get("model_name"),
                    temperature=user_config.get("temperature", 0.7),
                    max_tokens=user_config.get("max_tokens", 2000),
                )
        return self.get_provider(provider_name)

    def set_default_provider(self, name: str) -> None:
        self._default_provider_name = name

    def list_available_providers(self) -> List[Dict[str, Any]]:
        """返回已配置的Provider列表及其状态"""
        provider_classes = {
            "openai": OpenAIProvider,
            "deepseek": DeepSeekProvider,
            "anthropic": AnthropicProvider,
            "baidu": BaiduProvider,
            "aliyun": AliyunProvider,
            "tencent": TencentProvider,
            "zhipu": ZhipuProvider,
            "moonshot": MoonshotProvider,
            "qwen": QwenProvider,
            "siliconflow": SiliconFlowProvider,
            "minimax": MiniMaxProvider,
        }

        results = []
        for name, ProviderClass in provider_classes.items():
            try:
                provider = ProviderClass()
                is_available, error_msg = provider.check_config()
                results.append({
                    "name": name,
                    "available": is_available,
                    "error": error_msg if not is_available else None,
                    "configured": is_available,
                })
            except Exception as e:
                results.append({
                    "name": name,
                    "available": False,
                    "error": str(e),
                    "configured": False,
                })

        # 检查OpenAI兼容配置
        if settings.OPENAI_COMPATIBLE_API_KEY and settings.OPENAI_COMPATIBLE_BASE_URL:
            results.append({
                "name": "openai_compatible",
                "available": True,
                "error": None,
                "configured": True,
            })

        return results

    def check_provider(self, provider_name: Optional[str] = None) -> Dict[str, Any]:
        """检查指定Provider的配置状态"""
        try:
            provider = self.get_provider(provider_name)
            is_available, error_msg = provider.check_config()
            return {
                "provider": provider_name or self._default_provider_name,
                "available": is_available,
                "error": error_msg if not is_available else None,
            }
        except Exception as e:
            return {
                "provider": provider_name or self._default_provider_name,
                "available": False,
                "error": str(e),
            }

    async def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        provider_name = provider or self._default_provider_name
        if metadata:
            from app.core.ai_engine.metrics import set_llm_context
            set_llm_context(**metadata)
        start = time.monotonic()
        status, err, completion, model = "success", None, "", ""
        try:
            llm = self.get_provider(provider)
            model = getattr(llm, "model", "") or ""
            # 先检查配置
            is_available, error_msg = llm.check_config()
            if not is_available:
                raise RuntimeError(error_msg)
            completion = await llm.generate(prompt, temperature, max_tokens)
            return completion
        except httpx.HTTPStatusError as e:
            status, err = "error", f"LLM API error: {e.response.status_code} - {e.response.text}"
            raise RuntimeError(err)
        except httpx.ConnectError:
            status, err = "error", "LLM service unavailable, please check network connection"
            raise RuntimeError(err)
        except Exception as e:
            status, err = "error", f"LLM generation failed: {str(e)}"
            raise RuntimeError(err)
        finally:
            latency = int((time.monotonic() - start) * 1000)
            from app.core.ai_engine.metrics import record_llm_call_sync
            record_llm_call_sync(provider_name, model, prompt, completion, latency, status, err)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        provider_name = provider or self._default_provider_name
        if metadata:
            from app.core.ai_engine.metrics import set_llm_context
            set_llm_context(**metadata)
        # 合并 prompt 文本用于 token 估算
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)
        start = time.monotonic()
        status, err, completion, model = "success", None, "", ""
        try:
            llm = self.get_provider(provider)
            model = getattr(llm, "model", "") or ""
            # 先检查配置
            is_available, error_msg = llm.check_config()
            if not is_available:
                raise RuntimeError(error_msg)
            completion = await llm.chat(messages, temperature, max_tokens)
            return completion
        except httpx.HTTPStatusError as e:
            status, err = "error", f"LLM API error: {e.response.status_code} - {e.response.text}"
            raise RuntimeError(err)
        except httpx.ConnectError:
            status, err = "error", "LLM service unavailable, please check network connection"
            raise RuntimeError(err)
        except Exception as e:
            status, err = "error", f"LLM chat failed: {str(e)}"
            raise RuntimeError(err)
        finally:
            latency = int((time.monotonic() - start) * 1000)
            from app.core.ai_engine.metrics import record_llm_call_sync
            record_llm_call_sync(provider_name, model, prompt_text, completion, latency, status, err)

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        provider_name = provider or self._default_provider_name
        if metadata:
            from app.core.ai_engine.metrics import set_llm_context
            set_llm_context(**metadata)
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)
        start = time.monotonic()
        status, err, completion, model = "success", None, "", ""
        try:
            llm = self.get_provider(provider)
            model = getattr(llm, "model", "") or ""
            # 先检查配置
            is_available, error_msg = llm.check_config()
            if not is_available:
                raise RuntimeError(error_msg)
            async for chunk in llm.stream_chat(messages, temperature, max_tokens):
                completion += chunk
                yield chunk
        except httpx.HTTPStatusError as e:
            status, err = "error", f"LLM API error: {e.response.status_code} - {e.response.text}"
            raise RuntimeError(err)
        except httpx.ConnectError:
            status, err = "error", "LLM service unavailable, please check network connection"
            raise RuntimeError(err)
        except Exception as e:
            status, err = "error", f"LLM stream failed: {str(e)}"
            raise RuntimeError(err)
        finally:
            latency = int((time.monotonic() - start) * 1000)
            from app.core.ai_engine.metrics import record_llm_call_sync
            record_llm_call_sync(provider_name, model, prompt_text, completion, latency, status, err)

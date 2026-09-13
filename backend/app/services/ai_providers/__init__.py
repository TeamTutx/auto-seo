from app.config import settings

from .anthropic import AnthropicProvider
from .base import AIProvider, AIProviderError
from .openai import OpenAIProvider

_PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}


def get_ai_provider() -> AIProvider:
    key = settings.ai_provider.lower()
    try:
        provider_cls = _PROVIDERS[key]
    except KeyError:
        raise AIProviderError(
            f"Unknown AI_PROVIDER '{settings.ai_provider}'. Choose one of: {', '.join(_PROVIDERS)}."
        )
    return provider_cls()


__all__ = ["AIProvider", "AIProviderError", "get_ai_provider"]

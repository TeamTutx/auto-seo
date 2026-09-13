"""Common contract every AI-suggestion vendor integration implements.

Mirrors app/services/rank_providers: one generic method (complete) rather
than a method per suggestion type, since AI suggestions will grow beyond
just meta descriptions (title rewrites, content briefs - REQUIREMENTS.md
§2.7) without needing a new provider method each time. The prompt for a
specific suggestion type lives in app/services/ai_suggestions.py, not here.
"""
from abc import ABC, abstractmethod


class AIProviderError(Exception):
    pass


class AIProvider(ABC):
    name: str

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 300) -> str:
        """Return the model's text completion for the given prompts."""

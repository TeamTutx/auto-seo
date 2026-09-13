import httpx

from app.config import settings

from .base import AIProvider, AIProviderError


class AnthropicProvider(AIProvider):
    name = "anthropic"

    URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"
    MODEL = "claude-haiku-4-5-20251001"  # cheap/fast - plenty for short copywriting tasks

    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 300) -> str:
        if not settings.anthropic_api_key:
            raise AIProviderError("Anthropic credentials are not configured (ANTHROPIC_API_KEY).")

        payload = {
            "model": self.MODEL,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        try:
            response = httpx.post(
                self.URL,
                json=payload,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": self.API_VERSION,
                },
                timeout=30.0,
            )
        except httpx.TransportError as exc:
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise AIProviderError(f"Anthropic returned a non-JSON {response.status_code} response.")

        if data.get("type") == "error":
            raise AIProviderError(f"Anthropic error: {data['error'].get('message', 'unknown error')}")

        try:
            return "".join(block["text"] for block in data["content"] if block.get("type") == "text")
        except (KeyError, TypeError):
            raise AIProviderError("Anthropic response did not contain a completion.")

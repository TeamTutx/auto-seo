import httpx

from app.config import settings

from .base import AIProvider, AIProviderError


class OpenAIProvider(AIProvider):
    name = "openai"

    URL = "https://api.openai.com/v1/chat/completions"
    MODEL = "gpt-4o-mini"  # cheap/fast - plenty for short copywriting tasks like a meta description

    def complete(self, system_prompt: str, user_prompt: str, max_tokens: int = 300) -> str:
        if not settings.openai_api_key:
            raise AIProviderError("OpenAI credentials are not configured (OPENAI_API_KEY).")

        payload = {
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.5,
        }

        try:
            response = httpx.post(
                self.URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                timeout=30.0,
            )
        except httpx.TransportError as exc:
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise AIProviderError(f"OpenAI returned a non-JSON {response.status_code} response.")

        if "error" in data:
            raise AIProviderError(f"OpenAI error: {data['error'].get('message', 'unknown error')}")

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise AIProviderError("OpenAI response did not contain a completion.")

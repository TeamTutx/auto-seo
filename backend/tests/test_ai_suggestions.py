import app.services.ai_suggestions as ai_suggestions
from app.services.ai_providers.base import AIProvider

HTML = """
<html>
<head><title>Vitamin C Brightening Serum</title></head>
<body><p>Our vitamin C serum brightens skin and evens tone over four weeks of daily use.</p></body>
</html>
"""


class _FakeProvider(AIProvider):
    name = "fake"

    def __init__(self):
        self.calls = []

    def complete(self, system_prompt, user_prompt, max_tokens=300):
        self.calls.append((system_prompt, user_prompt, max_tokens))
        return "  A brightening vitamin C serum that evens tone in four weeks.  "


def test_generate_meta_description_includes_page_context_in_prompt(monkeypatch):
    provider = _FakeProvider()
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: provider)

    result = ai_suggestions.generate_meta_description(HTML, "https://example.com/serum", "vitamin c serum")

    assert result == "A brightening vitamin C serum that evens tone in four weeks."
    assert len(provider.calls) == 1
    _, user_prompt, max_tokens = provider.calls[0]
    assert "Vitamin C Brightening Serum" in user_prompt
    assert "vitamin c serum" in user_prompt
    assert "brightens skin and evens tone" in user_prompt
    assert max_tokens < 300  # short by design, this isn't a content brief


def test_generate_meta_description_omits_keyword_line_when_none_set(monkeypatch):
    provider = _FakeProvider()
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: provider)

    ai_suggestions.generate_meta_description(HTML, "https://example.com/serum", None)

    _, user_prompt, _ = provider.calls[0]
    assert "Target keyword" not in user_prompt

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


def test_generate_title_tag_includes_page_context_in_prompt(monkeypatch):
    provider = _FakeProvider()
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: provider)

    ai_suggestions.generate_title_tag(HTML, "https://example.com/serum", "vitamin c serum")

    assert len(provider.calls) == 1
    system_prompt, user_prompt, max_tokens = provider.calls[0]
    assert "title tag" in system_prompt.lower()
    assert "Vitamin C Brightening Serum" in user_prompt
    assert "vitamin c serum" in user_prompt
    assert max_tokens < 300


def test_generate_heading_suggestion_includes_page_context_in_prompt(monkeypatch):
    provider = _FakeProvider()
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: provider)

    result = ai_suggestions.generate_heading_suggestion(HTML, "https://example.com/serum", "vitamin c serum")

    assert result == "A brightening vitamin C serum that evens tone in four weeks."
    system_prompt, user_prompt, _ = provider.calls[0]
    assert "heading" in system_prompt.lower()
    assert "vitamin c serum" in user_prompt


def test_generate_readability_suggestion_uses_the_opening_passage(monkeypatch):
    provider = _FakeProvider()
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: provider)

    ai_suggestions.generate_readability_suggestion(HTML, "https://example.com/serum", None)

    system_prompt, user_prompt, _ = provider.calls[0]
    assert "simpl" in system_prompt.lower()
    assert "brightens skin and evens tone" in user_prompt
    assert "Target keyword" not in user_prompt


ALT_TEXT_HTML = """
<html>
<head><title>Skincare shop</title></head>
<body>
  <img src="/serum.jpg">
  <img src="/toner.jpg" alt="Already has alt text">
  <div>Rose water toner for daily use.<img src="/toner-detail.jpg"></div>
</body>
</html>
"""


def test_generate_alt_text_suggestions_skips_images_that_already_have_alt(monkeypatch):
    class _AltProvider(AIProvider):
        name = "fake"

        def complete(self, system_prompt, user_prompt, max_tokens=300):
            return "1. Vitamin C serum bottle\n2. Rose water toner bottle on a shelf"

    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: _AltProvider())

    result = ai_suggestions.generate_alt_text_suggestions(ALT_TEXT_HTML, "https://example.com/shop")

    assert result == [
        {"src": "/serum.jpg", "suggested_alt": "Vitamin C serum bottle"},
        {"src": "/toner-detail.jpg", "suggested_alt": "Rose water toner bottle on a shelf"},
    ]


def test_generate_alt_text_suggestions_returns_empty_list_when_nothing_missing(monkeypatch):
    html = '<html><body><img src="/x.jpg" alt="Already described"></body></html>'
    calls = []
    monkeypatch.setattr(
        ai_suggestions, "get_ai_provider", lambda: calls.append(1) or _FakeProvider()
    )

    result = ai_suggestions.generate_alt_text_suggestions(html, "https://example.com/shop")

    assert result == []
    assert calls == []  # never even calls the AI provider - nothing to ask about


def test_generate_internal_linking_suggestions_lists_candidate_pages(monkeypatch):
    provider = _FakeProvider()
    monkeypatch.setattr(ai_suggestions, "get_ai_provider", lambda: provider)

    ai_suggestions.generate_internal_linking_suggestions(
        HTML,
        "https://example.com/serum",
        [("https://example.com/toner", "rose water toner"), ("https://example.com/about", None)],
    )

    system_prompt, user_prompt, _ = provider.calls[0]
    assert "internal link" in system_prompt.lower()
    assert "https://example.com/toner" in user_prompt
    assert "rose water toner" in user_prompt
    assert "https://example.com/about" in user_prompt

from app.services.ai_providers.base import AIProvider
from app.services.keyword_opportunities import (
    _parse_opportunity_lines,
    generate_keyword_opportunities,
    generate_ranking_action_plan,
)
from app.services.rank_providers.base import SerpResult

HTML = """
<html>
<head><title>Vitamin C Brightening Serum</title></head>
<body><p>Our vitamin C serum brightens skin and evens tone over four weeks of daily use.</p></body>
</html>
"""

COMPETITORS = [
    SerpResult(position=1, title="Best Vitamin C Serums for Dark Spots", domain="a.com", url="https://a.com"),
    SerpResult(position=2, title="Vitamin C Serum Guide for Sensitive Skin", domain="b.com", url="https://b.com"),
]


class _FakeProvider(AIProvider):
    name = "fake"

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def complete(self, system_prompt, user_prompt, max_tokens=300):
        self.calls.append((system_prompt, user_prompt, max_tokens))
        return self.reply


def test_generate_keyword_opportunities_includes_page_and_competitor_context(monkeypatch):
    import app.services.keyword_opportunities as keyword_opportunities

    provider = _FakeProvider("vitamin c serum for dark spots - Competitors rank for this variant\n")
    monkeypatch.setattr(keyword_opportunities, "get_ai_provider", lambda: provider)

    result = generate_keyword_opportunities(HTML, "https://example.com/serum", "vitamin c serum", COMPETITORS)

    assert result == [
        {"keyword": "vitamin c serum for dark spots", "reason": "Competitors rank for this variant"}
    ]
    _, user_prompt, _ = provider.calls[0]
    assert "vitamin c serum" in user_prompt
    assert "Best Vitamin C Serums for Dark Spots" in user_prompt
    assert "brightens skin and evens tone" in user_prompt


def test_generate_keyword_opportunities_with_no_competitors(monkeypatch):
    import app.services.keyword_opportunities as keyword_opportunities

    provider = _FakeProvider("sensitive skin serum - No direct competitor gap found, but related\n")
    monkeypatch.setattr(keyword_opportunities, "get_ai_provider", lambda: provider)

    generate_keyword_opportunities(HTML, "https://example.com/serum", "vitamin c serum", [])

    _, user_prompt, _ = provider.calls[0]
    assert "(none found)" in user_prompt


def test_parse_opportunity_lines_handles_dash_and_colon_formats():
    raw = "keyword one - reason one\nkeyword two: reason two\n- keyword three - reason three"
    assert _parse_opportunity_lines(raw) == [
        {"keyword": "keyword one", "reason": "reason one"},
        {"keyword": "keyword two", "reason": "reason two"},
        {"keyword": "keyword three", "reason": "reason three"},
    ]


def test_parse_opportunity_lines_skips_blank_lines():
    raw = "keyword one - reason one\n\n\nkeyword two - reason two"
    assert len(_parse_opportunity_lines(raw)) == 2


def test_generate_ranking_action_plan_includes_page_and_competitor_context(monkeypatch):
    import app.services.keyword_opportunities as keyword_opportunities

    provider = _FakeProvider("Add a dedicated ingredients section.\nCover sensitive-skin use cases.")
    monkeypatch.setattr(keyword_opportunities, "get_ai_provider", lambda: provider)

    result = generate_ranking_action_plan(HTML, "https://example.com/serum", "vitamin c serum", COMPETITORS)

    assert result == "Add a dedicated ingredients section.\nCover sensitive-skin use cases."
    system_prompt, user_prompt, _ = provider.calls[0]
    assert "action plan" in system_prompt.lower()
    assert "vitamin c serum" in user_prompt
    assert "Best Vitamin C Serums for Dark Spots" in user_prompt
    assert "brightens skin and evens tone" in user_prompt


def test_generate_ranking_action_plan_with_no_competitors(monkeypatch):
    import app.services.keyword_opportunities as keyword_opportunities

    provider = _FakeProvider("Publish original content targeting this term directly.")
    monkeypatch.setattr(keyword_opportunities, "get_ai_provider", lambda: provider)

    generate_ranking_action_plan(HTML, "https://example.com/serum", "vitamin c serum", [])

    _, user_prompt, _ = provider.calls[0]
    assert "low-competition keyword" in user_prompt

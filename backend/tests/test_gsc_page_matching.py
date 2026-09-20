"""Matching a Signal page to the URL Search Console actually recorded.

Search Console's page filter is an exact string match against the canonical URL
*Google* chose. Sites disagree about trailing slashes - WordPress serves
/about/, Next.js serves /about - and one character of disagreement returns zero
rows, which is indistinguishable from "this page gets no search traffic". That
ambiguity is the bug these tests exist to prevent.
"""
import pytest

from app.services import gsc


@pytest.fixture
def calls(monkeypatch):
    """Capture every Search Analytics request and reply from a scripted map of
    page URL -> rows."""
    recorded = []
    responses = {}

    def fake_request(method, url, access_token, **kwargs):
        expression = kwargs["json"]["dimensionFilterGroups"][0]["filters"][0]["expression"]
        recorded.append(expression)
        return {"rows": responses.get(expression, [])}

    monkeypatch.setattr(gsc, "_request", fake_request)
    return recorded, responses


@pytest.mark.parametrize("stored, recorded_by_google", [
    ("https://example.com/about", "https://example.com/about/"),   # we lack the slash
    ("https://example.com/about/", "https://example.com/about"),   # we have one too many
    ("https://example.com/", "https://example.com"),               # the root, either way
])
def test_a_trailing_slash_mismatch_still_finds_the_data(calls, stored, recorded_by_google):
    asked, responses = calls
    responses[recorded_by_google] = [
        {"keys": ["seo audit"], "clicks": 3, "impressions": 90, "ctr": 0.03, "position": 7.2}
    ]

    rows = gsc.get_page_search_analytics("token", "sc-domain:example.com", stored)

    assert [r["query"] for r in rows] == ["seo audit"]
    assert asked == [stored, recorded_by_google]  # exact first, then the variant


def test_the_exact_url_is_preferred_and_costs_one_request(calls):
    """The common case must not pay for a second call."""
    asked, responses = calls
    responses["https://example.com/about"] = [
        {"keys": ["x"], "clicks": 1, "impressions": 2, "ctr": 0.5, "position": 1.0}
    ]

    gsc.get_page_search_analytics("token", "sc-domain:example.com", "https://example.com/about")

    assert asked == ["https://example.com/about"]


def test_a_page_with_genuinely_no_traffic_still_reports_nothing(calls):
    """The retry must not invent data - both forms empty means empty."""
    asked, _ = calls

    rows = gsc.get_page_search_analytics("token", "sc-domain:example.com", "https://example.com/quiet")

    assert rows == []
    assert len(asked) == 2  # it tried both before giving up


def test_the_daily_trend_gets_the_same_treatment(calls):
    """The site page's chart reads this one; a slash mismatch there drew an
    empty chart under a healthy page."""
    asked, responses = calls
    responses["https://example.com/about/"] = [
        {"keys": ["2026-09-01"], "clicks": 2, "impressions": 40, "position": 9.1}
    ]

    rows = gsc.get_page_daily_metrics("token", "sc-domain:example.com", "https://example.com/about")

    assert rows == [{"date": "2026-09-01", "clicks": 2, "impressions": 40, "position": 9.1}]
    assert asked == ["https://example.com/about", "https://example.com/about/"]


@pytest.mark.parametrize("url, expected", [
    ("https://x.com/a", ["https://x.com/a", "https://x.com/a/"]),
    ("https://x.com/a/", ["https://x.com/a/", "https://x.com/a"]),
    ("https://x.com/", ["https://x.com/", "https://x.com"]),
    # the slash belongs to the path, not the end of the string
    ("https://x.com/a?b=1", ["https://x.com/a?b=1", "https://x.com/a/?b=1"]),
])
def test_slash_variants(url, expected):
    assert gsc.slash_variants(url) == expected

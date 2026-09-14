import httpx
import pytest

from app.config import settings
from app.services.rank_providers.base import RankProviderError
from app.services.rank_providers.serpapi import SerpApiProvider

SERP_RESPONSE = {
    "organic_results": [
        {"position": 1, "title": "Competitor", "link": "https://competitor.com/a"},
        {"position": 2, "title": "Example", "link": "https://www.example.com/serum"},
        {"position": 3, "title": "Other", "link": "https://other.com/b"},
    ]
}


def test_parses_organic_results_in_order():
    results = SerpApiProvider.parse_serp(SERP_RESPONSE)
    assert [r.position for r in results] == [1, 2, 3]
    assert [r.domain for r in results] == ["competitor.com", "example.com", "other.com"]


def test_normalizes_www_prefix():
    results = SerpApiProvider.parse_serp(SERP_RESPONSE)
    assert results[1].domain == "example.com"


def test_handles_missing_organic_results():
    assert SerpApiProvider.parse_serp({}) == []


def test_fetch_rank_finds_target_via_parsed_serp(monkeypatch):
    provider = SerpApiProvider()
    monkeypatch.setattr(provider, "fetch_serp", lambda keyword, location_code, language_code, device: SerpApiProvider.parse_serp(SERP_RESPONSE))

    assert provider.fetch_rank("kw", "example.com", 2356, "en", "desktop") == 2
    assert provider.fetch_rank("kw", "not-ranked.com", 2356, "en", "desktop") is None


def test_fetch_serp_passes_num_results_through(monkeypatch):
    monkeypatch.setattr(settings, "serpapi_key", "test-key")
    captured = {}

    def fake_get(url, params, timeout):
        captured.update(params)
        return httpx.Response(200, json=SERP_RESPONSE, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    SerpApiProvider().fetch_serp("kw", 2356, "en", "desktop", num_results=15)
    assert captured["num"] == 15


def test_fetch_serp_retries_once_on_a_read_timeout(monkeypatch):
    monkeypatch.setattr(settings, "serpapi_key", "test-key")
    calls = []

    def fake_get(url, params, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out", request=httpx.Request("GET", url))
        return httpx.Response(200, json=SERP_RESPONSE, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    results = SerpApiProvider().fetch_serp("kw", 2356, "en", "desktop")
    assert len(calls) == 2
    assert [r.position for r in results] == [1, 2, 3]


def test_fetch_serp_raises_after_two_consecutive_timeouts(monkeypatch):
    monkeypatch.setattr(settings, "serpapi_key", "test-key")

    def fake_get(url, params, timeout):
        raise httpx.ReadTimeout("timed out", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(RankProviderError, match="timed out twice"):
        SerpApiProvider().fetch_serp("kw", 2356, "en", "desktop")

import httpx
import pytest

from app.config import settings
from app.services.rank_providers.base import RankProviderError
from app.services.rank_providers.dataforseo import DataForSEOProvider

SERP_RESPONSE = {
    "status_code": 20000,
    "tasks": [{
        "result": [{
            "items": [
                {"type": "organic", "rank_absolute": 1, "domain": "competitor.com", "url": "https://competitor.com/a", "title": "Competitor"},
                {"type": "featured_snippet", "rank_absolute": 1, "domain": "competitor.com"},
                {"type": "organic", "rank_absolute": 2, "domain": "www.example.com", "url": "https://www.example.com/serum", "title": "Example"},
                {"type": "organic", "rank_absolute": 3, "domain": "other.com", "url": "https://other.com/b", "title": "Other"},
            ]
        }]
    }],
}


def test_parses_organic_results_in_order():
    results = DataForSEOProvider.parse_serp(SERP_RESPONSE)
    assert [r.position for r in results] == [1, 2, 3]
    assert [r.domain for r in results] == ["competitor.com", "example.com", "other.com"]


def test_normalizes_www_prefix():
    results = DataForSEOProvider.parse_serp(SERP_RESPONSE)
    assert results[1].domain == "example.com"  # not "www.example.com"


def test_ignores_non_organic_items():
    response = {
        "tasks": [{"result": [{"items": [
            {"type": "featured_snippet", "rank_absolute": 1, "domain": "example.com"},
        ]}]}]
    }
    assert DataForSEOProvider.parse_serp(response) == []


def test_handles_malformed_response():
    assert DataForSEOProvider.parse_serp({}) == []
    assert DataForSEOProvider.parse_serp({"tasks": []}) == []
    assert DataForSEOProvider.parse_serp({"tasks": [{"result": None}]}) == []


def test_fetch_rank_finds_target_via_parsed_serp(monkeypatch):
    provider = DataForSEOProvider()
    monkeypatch.setattr(provider, "fetch_serp", lambda keyword, location_code, language_code, device: DataForSEOProvider.parse_serp(SERP_RESPONSE))

    assert provider.fetch_rank("kw", "example.com", 2356, "en", "desktop") == 2
    assert provider.fetch_rank("kw", "www.example.com", 2356, "en", "desktop") == 2
    assert provider.fetch_rank("kw", "not-ranked.com", 2356, "en", "desktop") is None


def test_fetch_serp_passes_num_results_through_as_depth(monkeypatch):
    monkeypatch.setattr(settings, "dataforseo_login", "user")
    monkeypatch.setattr(settings, "dataforseo_password", "pass")
    captured = {}

    def fake_post(url, json, auth, timeout):
        captured.update(json[0])
        return httpx.Response(200, json=SERP_RESPONSE, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    DataForSEOProvider().fetch_serp("kw", 2356, "en", "desktop", num_results=15)
    assert captured["depth"] == 15


def test_fetch_serp_retries_once_on_a_read_timeout(monkeypatch):
    monkeypatch.setattr(settings, "dataforseo_login", "user")
    monkeypatch.setattr(settings, "dataforseo_password", "pass")
    calls = []

    def fake_post(url, json, auth, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out", request=httpx.Request("POST", url))
        return httpx.Response(200, json=SERP_RESPONSE, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    results = DataForSEOProvider().fetch_serp("kw", 2356, "en", "desktop")
    assert len(calls) == 2
    assert [r.position for r in results] == [1, 2, 3]


def test_fetch_serp_raises_after_two_consecutive_timeouts(monkeypatch):
    monkeypatch.setattr(settings, "dataforseo_login", "user")
    monkeypatch.setattr(settings, "dataforseo_password", "pass")

    def fake_post(url, json, auth, timeout):
        raise httpx.ReadTimeout("timed out", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(RankProviderError, match="timed out twice"):
        DataForSEOProvider().fetch_serp("kw", 2356, "en", "desktop")

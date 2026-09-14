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

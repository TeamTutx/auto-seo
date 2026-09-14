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

from app.services.rank_providers.serpapi import SerpApiProvider

SERP_RESPONSE = {
    "organic_results": [
        {"position": 1, "title": "Competitor", "link": "https://competitor.com/a"},
        {"position": 2, "title": "Example", "link": "https://www.example.com/serum"},
        {"position": 3, "title": "Other", "link": "https://other.com/b"},
    ]
}


def test_finds_rank_for_target_domain():
    assert SerpApiProvider.extract_rank(SERP_RESPONSE, "example.com") == 2


def test_matches_regardless_of_www_prefix():
    assert SerpApiProvider.extract_rank(SERP_RESPONSE, "www.example.com") == 2


def test_returns_none_when_domain_not_present():
    assert SerpApiProvider.extract_rank(SERP_RESPONSE, "not-ranked.com") is None


def test_handles_missing_organic_results():
    assert SerpApiProvider.extract_rank({}, "example.com") is None

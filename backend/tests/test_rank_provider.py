from app.services.rank_provider import extract_rank

SERP_RESPONSE = {
    "status_code": 20000,
    "tasks": [{
        "result": [{
            "items": [
                {"type": "organic", "rank_absolute": 1, "domain": "competitor.com", "url": "https://competitor.com/a"},
                {"type": "featured_snippet", "rank_absolute": 1, "domain": "competitor.com"},
                {"type": "organic", "rank_absolute": 2, "domain": "www.example.com", "url": "https://www.example.com/serum"},
                {"type": "organic", "rank_absolute": 3, "domain": "other.com", "url": "https://other.com/b"},
            ]
        }]
    }],
}


def test_finds_rank_for_target_domain():
    assert extract_rank(SERP_RESPONSE, "example.com") == 2


def test_matches_regardless_of_www_prefix():
    assert extract_rank(SERP_RESPONSE, "www.example.com") == 2


def test_returns_none_when_domain_not_present():
    assert extract_rank(SERP_RESPONSE, "not-ranked.com") is None


def test_ignores_non_organic_items():
    response = {
        "tasks": [{"result": [{"items": [
            {"type": "featured_snippet", "rank_absolute": 1, "domain": "example.com"},
        ]}]}]
    }
    assert extract_rank(response, "example.com") is None


def test_handles_malformed_response():
    assert extract_rank({}, "example.com") is None
    assert extract_rank({"tasks": []}, "example.com") is None
    assert extract_rank({"tasks": [{"result": None}]}, "example.com") is None

from app.services.competitors import get_competitors
from app.services.rank_providers.base import RankProvider, SerpResult

SAMPLE_SERP = [
    SerpResult(position=1, title="Competitor A", domain="competitor-a.com", url="https://competitor-a.com/"),
    SerpResult(position=2, title="Example (own site)", domain="example.com", url="https://example.com/page"),
    SerpResult(position=3, title="Competitor B", domain="competitor-b.com", url="https://competitor-b.com/"),
]


class _FakeProvider(RankProvider):
    name = "fake"

    def __init__(self):
        self.calls = []

    def fetch_serp(self, keyword, location_code, language_code, device, num_results=100):
        self.calls.append(num_results)
        return SAMPLE_SERP


def test_get_competitors_requests_a_shallow_scan_not_the_full_100(monkeypatch):
    import app.services.competitors as competitors_service

    provider = _FakeProvider()
    monkeypatch.setattr(competitors_service, "get_rank_provider", lambda: provider)

    get_competitors("kw", "https://example.com/page", 2356, "en", "desktop", limit=5)

    assert provider.calls == [15]  # limit + 10, nowhere near the rank-check default of 100


def test_get_competitors_still_excludes_own_domain_and_respects_limit(monkeypatch):
    import app.services.competitors as competitors_service

    provider = _FakeProvider()
    monkeypatch.setattr(competitors_service, "get_rank_provider", lambda: provider)

    results = get_competitors("kw", "https://example.com/page", 2356, "en", "desktop", limit=1)

    assert [r.domain for r in results] == ["competitor-a.com"]

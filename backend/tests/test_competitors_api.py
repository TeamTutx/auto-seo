import pytest

import app.services.competitors as competitors_service
from app.services.rank_providers.base import RankProvider, SerpResult
from tests.conftest import make_page, register_and_login

SAMPLE_SERP = [
    SerpResult(position=1, title="Competitor A", domain="competitor-a.com", url="https://competitor-a.com/"),
    SerpResult(position=2, title="Example (own site)", domain="example.com", url="https://example.com/page"),
    SerpResult(position=3, title="Competitor B", domain="competitor-b.com", url="https://competitor-b.com/"),
]


class _FakeSerpProvider(RankProvider):
    name = "fake-serp"

    def fetch_serp(self, keyword, location_code, language_code, device):
        return SAMPLE_SERP


@pytest.fixture
def fake_serp(monkeypatch):
    monkeypatch.setattr(competitors_service, "get_rank_provider", lambda: _FakeSerpProvider())


def test_competitors_excludes_own_domain_and_spends_a_credit(client, fake_serp):
    headers = register_and_login(client, "comp1@test.dev")
    page_id = make_page(client, headers, domain="example.com", url="https://example.com/page")

    resp = client.post(f"/pages/{page_id}/keywords/competitors", json={"keyword": "a"}, headers=headers)
    assert resp.status_code == 200
    domains = [c["domain"] for c in resp.json()]
    assert domains == ["competitor-a.com", "competitor-b.com"]

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 2


def test_competitors_requires_credits(client, fake_serp, db):
    from tests.conftest import grant_credits

    headers = register_and_login(client, "comp2@test.dev")
    page_id = make_page(client, headers)
    grant_credits(db, "comp2@test.dev", 0)

    resp = client.post(f"/pages/{page_id}/keywords/competitors", json={"keyword": "a"}, headers=headers)
    assert resp.status_code == 402

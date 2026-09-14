import pytest

import app.routers.keywords as keywords_router
import app.services.competitors as competitors_service
from app.services.rank_providers.base import RankProvider, SerpResult
from tests.conftest import grant_credits, make_page, register_and_login

SAMPLE_SERP = [
    SerpResult(position=1, title="Competitor A", domain="competitor-a.com", url="https://competitor-a.com/"),
]

FAKE_HTML = "<html><head><title>Serum</title></head><body>Vitamin C serum for glowing skin.</body></html>"


class _FakeSerpProvider(RankProvider):
    name = "fake-serp"

    def fetch_serp(self, keyword, location_code, language_code, device, num_results=100):
        return SAMPLE_SERP


@pytest.fixture
def fake_serp(monkeypatch):
    monkeypatch.setattr(competitors_service, "get_rank_provider", lambda: _FakeSerpProvider())


def test_action_plan_returns_plan_and_spends_two_credits(client, fake_serp, monkeypatch):
    monkeypatch.setattr(keywords_router, "fetch_html", lambda url: FAKE_HTML)
    monkeypatch.setattr(
        keywords_router,
        "generate_ranking_action_plan",
        lambda html, url, keyword, competitors: "Add a dedicated FAQ section.\nCover ingredient sourcing.",
    )

    headers = register_and_login(client, "plan1@test.dev")
    page_id = make_page(client, headers, domain="example.com", url="https://example.com/page")

    resp = client.post(f"/pages/{page_id}/keywords/action-plan", json={"keyword": "vitamin c serum"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"plan": "Add a dedicated FAQ section.\nCover ingredient sourcing."}

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 1  # started at 3, spent 2


def test_action_plan_requires_two_credits(client, fake_serp, db):
    headers = register_and_login(client, "plan2@test.dev")
    page_id = make_page(client, headers)
    grant_credits(db, "plan2@test.dev", 1)

    resp = client.post(f"/pages/{page_id}/keywords/action-plan", json={"keyword": "vitamin c serum"}, headers=headers)
    assert resp.status_code == 402


def test_action_plan_ai_failure_does_not_spend_the_second_credit(client, fake_serp, monkeypatch):
    from app.services.ai_providers import AIProviderError

    monkeypatch.setattr(keywords_router, "fetch_html", lambda url: FAKE_HTML)

    def _boom(html, url, keyword, competitors):
        raise AIProviderError("OpenAI credentials are not configured (OPENAI_API_KEY).")

    monkeypatch.setattr(keywords_router, "generate_ranking_action_plan", _boom)

    headers = register_and_login(client, "plan3@test.dev")
    page_id = make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/keywords/action-plan", json={"keyword": "vitamin c serum"}, headers=headers)
    assert resp.status_code == 502

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 2  # only the competitor-lookup credit was spent

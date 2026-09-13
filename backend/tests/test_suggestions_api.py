import app.routers.suggestions as suggestions_router
from tests.conftest import make_page, register_and_login

FAKE_HTML = "<html><head><title>Serum</title></head><body>Vitamin C serum for glowing skin.</body></html>"


def test_generates_suggestion_and_spends_a_credit(client, monkeypatch):
    monkeypatch.setattr(suggestions_router, "fetch_html", lambda url: FAKE_HTML)
    monkeypatch.setattr(
        suggestions_router,
        "generate_meta_description",
        lambda html, url, keyword: "Brighten skin with our vitamin C serum, formulated for daily glow.",
    )

    headers = register_and_login(client, "ai1@test.dev")
    page_id = make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/suggestions/meta-description", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"suggestion": "Brighten skin with our vitamin C serum, formulated for daily glow."}

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 2  # started at 3, spent 1


def test_provider_error_surfaces_as_502_and_does_not_spend_a_credit(client, monkeypatch):
    from app.services.ai_providers import AIProviderError

    monkeypatch.setattr(suggestions_router, "fetch_html", lambda url: FAKE_HTML)

    def _boom(html, url, keyword):
        raise AIProviderError("OpenAI credentials are not configured (OPENAI_API_KEY).")

    monkeypatch.setattr(suggestions_router, "generate_meta_description", _boom)

    headers = register_and_login(client, "ai2@test.dev")
    page_id = make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/suggestions/meta-description", headers=headers)
    assert resp.status_code == 502

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 3  # unchanged - never charge on failure


def test_out_of_credits_blocks_before_calling_the_provider(client, monkeypatch, db):
    from tests.conftest import grant_credits

    calls = []
    monkeypatch.setattr(suggestions_router, "fetch_html", lambda url: FAKE_HTML)
    monkeypatch.setattr(
        suggestions_router, "generate_meta_description", lambda html, url, keyword: calls.append(1) or "x"
    )

    headers = register_and_login(client, "ai3@test.dev")
    page_id = make_page(client, headers)
    grant_credits(db, "ai3@test.dev", 0)

    resp = client.post(f"/pages/{page_id}/suggestions/meta-description", headers=headers)
    assert resp.status_code == 402
    assert calls == []  # provider never called once credits are exhausted

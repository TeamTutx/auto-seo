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


def test_title_tag_suggestion_endpoint(client, monkeypatch):
    monkeypatch.setattr(suggestions_router, "fetch_html", lambda url: FAKE_HTML)
    monkeypatch.setattr(
        suggestions_router,
        "generate_title_tag",
        lambda html, url, keyword: "Vitamin C Serum for Glowing, Even-Toned Skin",
    )

    headers = register_and_login(client, "ai4@test.dev")
    page_id = make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/suggestions/title-tag", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"suggestion": "Vitamin C Serum for Glowing, Even-Toned Skin"}

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 2


def test_heading_suggestion_endpoint(client, monkeypatch):
    monkeypatch.setattr(suggestions_router, "fetch_html", lambda url: FAKE_HTML)
    monkeypatch.setattr(
        suggestions_router, "generate_heading_suggestion", lambda html, url, keyword: "H1: Vitamin C Serum"
    )

    headers = register_and_login(client, "ai5@test.dev")
    page_id = make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/suggestions/heading", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"suggestion": "H1: Vitamin C Serum"}

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 2


def test_readability_suggestion_endpoint(client, monkeypatch):
    monkeypatch.setattr(suggestions_router, "fetch_html", lambda url: FAKE_HTML)
    monkeypatch.setattr(
        suggestions_router, "generate_readability_suggestion", lambda html, url, keyword: "Simpler text."
    )

    headers = register_and_login(client, "ai6@test.dev")
    page_id = make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/suggestions/readability", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"suggestion": "Simpler text."}


def test_alt_text_suggestion_endpoint_spends_a_credit_when_images_are_suggested(client, monkeypatch):
    monkeypatch.setattr(suggestions_router, "fetch_html", lambda url: FAKE_HTML)
    monkeypatch.setattr(
        suggestions_router,
        "generate_alt_text_suggestions",
        lambda html, url: [{"src": "/serum.jpg", "suggested_alt": "Vitamin C serum bottle"}],
    )

    headers = register_and_login(client, "ai7@test.dev")
    page_id = make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/suggestions/alt-text", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == [{"src": "/serum.jpg", "suggested_alt": "Vitamin C serum bottle"}]

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 2


def test_alt_text_suggestion_endpoint_does_not_spend_a_credit_when_nothing_is_missing(client, monkeypatch):
    monkeypatch.setattr(suggestions_router, "fetch_html", lambda url: FAKE_HTML)
    monkeypatch.setattr(suggestions_router, "generate_alt_text_suggestions", lambda html, url: [])

    headers = register_and_login(client, "ai8@test.dev")
    page_id = make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/suggestions/alt-text", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 3  # nothing to suggest - never charged


def test_internal_links_suggestion_endpoint_requires_a_sibling_page(client, monkeypatch):
    calls = []
    monkeypatch.setattr(suggestions_router, "fetch_html", lambda url: calls.append(1) or FAKE_HTML)

    headers = register_and_login(client, "ai9@test.dev")
    page_id = make_page(client, headers)

    resp = client.post(f"/pages/{page_id}/suggestions/internal-links", headers=headers)
    assert resp.status_code == 200
    assert "Add more pages" in resp.json()["suggestion"]
    assert calls == []  # no other pages on the site - never even fetches this one

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 3  # unchanged


def test_internal_links_suggestion_endpoint_with_a_sibling_page(client, monkeypatch):
    monkeypatch.setattr(suggestions_router, "fetch_html", lambda url: FAKE_HTML)
    monkeypatch.setattr(
        suggestions_router,
        "generate_internal_linking_suggestions",
        lambda html, url, candidates: f"Link to {candidates[0][0]} using anchor text like \"toner\"",
    )

    headers = register_and_login(client, "ai10@test.dev")
    site = client.post("/sites", json={"domain": "example.com"}, headers=headers).json()
    page1 = client.post(
        f"/sites/{site['id']}/pages", json={"url": "https://example.com/serum"}, headers=headers
    ).json()
    client.post(f"/sites/{site['id']}/pages", json={"url": "https://example.com/toner"}, headers=headers)

    resp = client.post(f"/pages/{page1['id']}/suggestions/internal-links", headers=headers)
    assert resp.status_code == 200
    assert "https://example.com/toner" in resp.json()["suggestion"]

    me = client.get("/auth/me", headers=headers).json()
    assert me["credits_balance"] == 2  # spent 1 credit, unlike the no-sibling-pages case

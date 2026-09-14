import app.routers.google_integration as google_integration_router
import app.services.ga as ga_service
import app.services.gsc as gsc_service
from app.config import settings
from app.security import create_access_token
from tests.conftest import register_and_login


def test_connect_returns_authorize_url_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-123")
    headers = register_and_login(client, "gi1@test.dev")

    resp = client.post("/integrations/google/connect", headers=headers)
    assert resp.status_code == 200
    assert "accounts.google.com" in resp.json()["authorize_url"]


def test_connect_without_client_id_configured_returns_400(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    headers = register_and_login(client, "gi2@test.dev")

    resp = client.post("/integrations/google/connect", headers=headers)
    assert resp.status_code == 400


def test_connect_requires_auth(client):
    resp = client.post("/integrations/google/connect")
    assert resp.status_code == 401


def test_callback_with_valid_state_and_code_saves_connection_and_redirects(client, monkeypatch):
    register_and_login(client, "gi3@test.dev")
    state = create_access_token(subject="gi3@test.dev")

    monkeypatch.setattr(
        google_integration_router,
        "exchange_code",
        lambda code: {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600, "scope": "a b"},
    )

    resp = client.get(
        f"/integrations/google/callback?code=abc&state={state}", follow_redirects=False
    )
    assert resp.status_code in (302, 303, 307)
    assert "google=connected" in resp.headers["location"]


def test_callback_with_invalid_state_redirects_with_error(client):
    resp = client.get("/integrations/google/callback?code=abc&state=garbage", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert "google_error" in resp.headers["location"]


def test_callback_when_exchange_fails_redirects_with_error(client, monkeypatch):
    from app.services.google_oauth import GoogleOAuthError

    register_and_login(client, "gi4@test.dev")
    state = create_access_token(subject="gi4@test.dev")

    def _boom(code):
        raise GoogleOAuthError("Malformed auth code.")

    monkeypatch.setattr(google_integration_router, "exchange_code", _boom)

    resp = client.get(f"/integrations/google/callback?code=bad&state={state}", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert "google_error" in resp.headers["location"]


def test_status_when_not_connected(client):
    headers = register_and_login(client, "gi5@test.dev")
    resp = client.get("/integrations/google/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"connected": False, "connected_at": None, "gsc_properties": [], "ga_properties": []}


def test_status_when_connected_lists_properties(client, monkeypatch):
    headers = register_and_login(client, "gi6@test.dev")
    state = create_access_token(subject="gi6@test.dev")
    monkeypatch.setattr(
        google_integration_router,
        "exchange_code",
        lambda code: {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600},
    )
    client.get(f"/integrations/google/callback?code=abc&state={state}", follow_redirects=False)

    monkeypatch.setattr(gsc_service, "list_properties", lambda token: ["sc-domain:example.com"])
    monkeypatch.setattr(
        ga_service, "list_properties", lambda token: [{"property_id": "12345", "display_name": "Example"}]
    )

    resp = client.get("/integrations/google/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["gsc_properties"] == ["sc-domain:example.com"]
    assert body["ga_properties"] == [{"property_id": "12345", "display_name": "Example"}]


def test_status_when_property_listing_fails_reports_connected_with_empty_lists(client, monkeypatch):
    headers = register_and_login(client, "gi7@test.dev")
    state = create_access_token(subject="gi7@test.dev")
    monkeypatch.setattr(
        google_integration_router,
        "exchange_code",
        lambda code: {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600},
    )
    client.get(f"/integrations/google/callback?code=abc&state={state}", follow_redirects=False)

    from app.services.gsc import GSCError

    def _boom(token):
        raise GSCError("nope")

    monkeypatch.setattr(gsc_service, "list_properties", _boom)
    monkeypatch.setattr(ga_service, "list_properties", lambda token: [])

    resp = client.get("/integrations/google/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["gsc_properties"] == []


def test_disconnect_removes_connection(client, monkeypatch):
    headers = register_and_login(client, "gi8@test.dev")
    state = create_access_token(subject="gi8@test.dev")
    monkeypatch.setattr(
        google_integration_router,
        "exchange_code",
        lambda code: {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600},
    )
    client.get(f"/integrations/google/callback?code=abc&state={state}", follow_redirects=False)

    resp = client.delete("/integrations/google", headers=headers)
    assert resp.status_code == 204

    status_resp = client.get("/integrations/google/status", headers=headers)
    assert status_resp.json()["connected"] is False

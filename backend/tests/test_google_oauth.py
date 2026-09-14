import httpx
import pytest

from app.config import settings
from app.services.google_oauth import GoogleOAuthError, build_authorize_url, exchange_code, refresh_access_token


def test_build_authorize_url_includes_offline_and_consent(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-123")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://localhost:8000/integrations/google/callback")

    url = build_authorize_url("state-abc")

    assert "client_id=client-123" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "state=state-abc" in url
    assert "webmasters.readonly" in url
    assert "analytics.readonly" in url


def test_build_authorize_url_without_client_id_configured_raises_clearly(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    with pytest.raises(GoogleOAuthError, match="not configured"):
        build_authorize_url("state-abc")


def test_exchange_code_returns_token_payload(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-123")
    monkeypatch.setattr(settings, "google_client_secret", "secret-456")

    def fake_post(url, data, timeout):
        assert data["code"] == "auth-code"
        assert data["grant_type"] == "authorization_code"
        return httpx.Response(
            200,
            json={"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600, "scope": "a b"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = exchange_code("auth-code")
    assert result["access_token"] == "at-1"
    assert result["refresh_token"] == "rt-1"


def test_exchange_code_without_credentials_configured_raises_clearly(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "")
    with pytest.raises(GoogleOAuthError, match="not configured"):
        exchange_code("auth-code")


def test_exchange_code_surfaces_googles_error_description(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-123")
    monkeypatch.setattr(settings, "google_client_secret", "secret-456")

    def fake_post(url, data, timeout):
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "Malformed auth code."},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(GoogleOAuthError, match="Malformed auth code"):
        exchange_code("bad-code")


def test_refresh_access_token_returns_new_token(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-123")
    monkeypatch.setattr(settings, "google_client_secret", "secret-456")

    def fake_post(url, data, timeout):
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "rt-1"
        return httpx.Response(
            200, json={"access_token": "at-2", "expires_in": 3600}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = refresh_access_token("rt-1")
    assert result["access_token"] == "at-2"


def test_transport_error_is_wrapped(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-123")
    monkeypatch.setattr(settings, "google_client_secret", "secret-456")

    def fake_post(url, data, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(GoogleOAuthError, match="Could not reach Google"):
        exchange_code("auth-code")

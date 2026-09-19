"""Sign in with Google - the advertised way into Signal.

The two Google calls (code exchange, profile lookup) are stubbed; everything
else, including the state cookie the browser really sends back, is exercised
through the app.
"""
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from sqlmodel import Session, select

import app.routers.auth_google as auth_google
from app.config import settings
from app.models import CreditTransaction, User
from app.services.google_oauth import GoogleOAuthError
from tests.conftest import get_user, register_and_login


@pytest.fixture
def google_configured(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    # http, like local dev: the state cookie is marked Secure for an https
    # callback (see the test below), which the test client can't send back.
    monkeypatch.setattr(settings, "google_login_redirect_uri", "http://testserver/auth/google/callback")
    monkeypatch.setattr(settings, "frontend_url", "https://app.test")


@pytest.fixture
def google_says(monkeypatch):
    """Stub the Google half: who the browser comes back as."""

    def _stub(email="new@gmail.com", email_verified=True, **extra):
        monkeypatch.setattr(auth_google, "exchange_login_code", lambda code: {"access_token": "ya29.token"})
        monkeypatch.setattr(
            auth_google,
            "fetch_userinfo",
            lambda token: {"sub": "10001", "email": email, "email_verified": email_verified, **extra},
        )

    return _stub


def _start(client):
    """Follow the first hop and return (the Google URL, the state nonce)."""
    resp = client.get("/auth/google/start", follow_redirects=False)
    query = parse_qs(urlparse(resp.headers["location"]).query)
    return resp, query


def _callback(client, state, **params):
    return client.get(
        "/auth/google/callback", params={"code": "auth-code", "state": state, **params}, follow_redirects=False
    )


def _fragment(resp):
    return dict(part.split("=", 1) for part in urlparse(resp.headers["location"]).fragment.split("&"))


# --- the hop out to Google ---

def test_start_redirects_to_google_asking_only_for_identity(client, google_configured):
    resp, query = _start(client)

    assert resp.status_code == 307
    assert resp.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert query["client_id"] == ["client-id.apps.googleusercontent.com"]
    assert query["redirect_uri"] == ["http://testserver/auth/google/callback"]
    # Signing in must not ask for Search Console or Analytics - that's a
    # separate, later consent from Settings.
    assert query["scope"] == ["openid email profile"]
    assert "access_type" not in query  # no refresh token to store for a login
    assert client.cookies.get("signal_oauth_state")  # paired with the state below


def test_the_state_cookie_is_secure_and_httponly_in_production(client, google_configured, monkeypatch):
    monkeypatch.setattr(settings, "google_login_redirect_uri", "https://api.signal-seo.in/auth/google/callback")

    resp = client.get("/auth/google/start", follow_redirects=False)

    cookie = resp.headers["set-cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie
    assert "SameSite=lax" in cookie  # still sent on Google's top-level redirect back
    assert "Path=/auth/google" in cookie


def test_start_without_a_configured_client_sends_the_user_back_with_an_error(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "frontend_url", "https://app.test")

    resp = client.get("/auth/google/start", follow_redirects=False)

    assert resp.headers["location"].startswith("https://app.test/login#error=")
    assert "GOOGLE_CLIENT_ID" in unquote(resp.headers["location"])


# --- coming back ---

def test_a_first_sign_in_creates_an_account_with_its_free_credits(client, db, google_configured, google_says):
    google_says(email="Newcomer@Gmail.com")
    _, query = _start(client)

    resp = _callback(client, query["state"][0])

    assert resp.status_code == 307
    token = unquote(_fragment(resp)["token"])
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "newcomer@gmail.com"  # normalised, so a second sign-in matches
    assert me["credits_balance"] == 3
    with Session(db) as session:
        user = session.exec(select(User).where(User.email == "newcomer@gmail.com")).one()
        ledger = session.exec(select(CreditTransaction).where(CreditTransaction.user_id == user.id)).all()
    assert [(t.delta, t.reason) for t in ledger] == [(3, "signup")]  # the ledger sums to the balance


def test_signing_in_again_reuses_the_account_and_does_not_re_grant_credits(client, db, google_configured, google_says):
    google_says(email="repeat@gmail.com")
    _, first = _start(client)
    _callback(client, first["state"][0])

    _, second = _start(client)
    resp = _callback(client, second["state"][0])

    assert "token" in _fragment(resp)
    with Session(db) as session:
        assert len(session.exec(select(User).where(User.email == "repeat@gmail.com")).all()) == 1
    assert get_user(db, "repeat@gmail.com").credits_balance == 3


def test_google_sign_in_lands_in_an_existing_password_account(client, db, google_configured, google_says):
    """Same person, same email - not a second account they'd have to notice."""
    register_and_login(client, "existing@test.dev")
    existing_id = get_user(db, "existing@test.dev").id
    google_says(email="EXISTING@test.dev")
    _, query = _start(client)

    resp = _callback(client, query["state"][0])

    token = unquote(_fragment(resp)["token"])
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["id"] == existing_id
    with Session(db) as session:
        assert len(session.exec(select(User)).all()) == 1


def test_an_unverified_google_email_is_refused(client, db, google_configured, google_says):
    """Otherwise anyone able to claim an unverified address on their own
    Workspace domain could walk into someone else's Signal account."""
    google_says(email="victim@test.dev", email_verified=False)
    _, query = _start(client)

    resp = _callback(client, query["state"][0])

    assert "isn't verified" in unquote(_fragment(resp)["error"])
    with Session(db) as session:
        assert session.exec(select(User)).all() == []


def test_a_state_that_does_not_match_the_cookie_is_refused(client, db, google_configured, google_says):
    google_says()
    _, query = _start(client)
    good_state = query["state"][0]

    client.cookies.delete("signal_oauth_state")
    no_cookie = _callback(client, good_state)

    _, fresh = _start(client)  # a real cookie, but someone else's state
    forged = _callback(client, "not-a-signed-state")

    for resp in (no_cookie, forged):
        assert "expired or came from somewhere else" in unquote(_fragment(resp)["error"])
    with Session(db) as session:
        assert session.exec(select(User)).all() == []


def test_pressing_cancel_on_googles_screen_is_not_an_error_page(client, google_configured):
    _, query = _start(client)

    resp = client.get(
        "/auth/google/callback", params={"error": "access_denied", "state": query["state"][0]}, follow_redirects=False
    )

    assert unquote(_fragment(resp)["error"]) == "Sign-in was cancelled."


def test_google_being_unreachable_shows_a_message_rather_than_a_500(client, google_configured, monkeypatch):
    _, query = _start(client)

    def boom(code):
        raise GoogleOAuthError("Could not reach Google: timed out")

    monkeypatch.setattr(auth_google, "exchange_login_code", boom)

    resp = _callback(client, query["state"][0])

    assert resp.status_code == 307 and "Could not reach Google" in unquote(_fragment(resp)["error"])


# --- the password fallback ---

def test_an_account_created_through_google_has_no_password_to_guess(client, db, google_configured, google_says):
    google_says(email="nopassword@gmail.com")
    _, query = _start(client)
    _callback(client, query["state"][0])

    for attempt in ["", "password", "hunter2"]:
        resp = client.post("/auth/login", data={"username": "nopassword@gmail.com", "password": attempt})
        assert resp.status_code == 401, attempt


def test_password_login_still_works_for_accounts_that_have_one(client, db):
    """Kept as a way back in if the OAuth client is ever misconfigured."""
    headers = register_and_login(client, "fallback@test.dev")

    assert client.get("/auth/me", headers=headers).status_code == 200

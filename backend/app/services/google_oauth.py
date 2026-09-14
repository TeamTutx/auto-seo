"""Google OAuth 2.0 - shared by Search Console and Analytics, since both are
just scopes on the same Google identity grant.

This is fundamentally different from the SerpApi/OpenAI integrations: those
are one static API key Signal calls on the vendor's behalf. This is a
per-user consent flow - each Signal user clicks "Connect Google" and grants
access to THEIR OWN Search Console/Analytics data through Google's real
login screen. There is no key that lets Signal (or an agent working on it)
fully exercise this without a registered Google Cloud OAuth client and a
human completing that consent screen - see backend/README.md for the setup
steps.
"""
from typing import List
from urllib.parse import urlencode

import httpx

from app.config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

SCOPES: List[str] = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
    "openid",
    "email",
]


class GoogleOAuthError(Exception):
    pass


def build_authorize_url(state: str) -> str:
    if not settings.google_client_id:
        raise GoogleOAuthError("Google integration is not configured (GOOGLE_CLIENT_ID).")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # required to get a refresh_token
        "prompt": "consent",  # forces a refresh_token even on a repeat connect
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _post_token_request(data: dict) -> dict:
    try:
        response = httpx.post(TOKEN_URL, data=data, timeout=15.0)
    except httpx.TransportError as exc:
        raise GoogleOAuthError(f"Could not reach Google: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        response.raise_for_status()
        raise GoogleOAuthError(f"Google returned a non-JSON {response.status_code} response.")

    if "error" in payload:
        raise GoogleOAuthError(payload.get("error_description") or payload["error"])
    return payload


def exchange_code(code: str) -> dict:
    """Returns the raw token response: access_token, refresh_token (only on
    first consent, or when prompt=consent forces it), expires_in, scope."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleOAuthError("Google integration is not configured (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET).")
    return _post_token_request({
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    })


def refresh_access_token(refresh_token: str) -> dict:
    """Returns a fresh access_token + expires_in (no new refresh_token)."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleOAuthError("Google integration is not configured (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET).")
    return _post_token_request({
        "refresh_token": refresh_token,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "grant_type": "refresh_token",
    })

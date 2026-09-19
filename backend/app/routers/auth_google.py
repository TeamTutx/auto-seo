"""Sign in with Google - the way people actually get into Signal.

Two hops, both plain browser navigations (no Bearer token exists yet):

  GET /auth/google/start     -> 307 to Google's consent screen
  GET /auth/google/callback  -> 307 to the frontend with a Signal token

The Signal token comes back in the URL *fragment*, not the query string: a
fragment is never sent to a server, so the token stays out of access logs,
proxies and the Referer header on the next click. The login page reads it,
stores it and rewrites the URL.

An account is matched by verified email address, so signing in with Google to an
address that already registered with a password lands in the same account rather
than creating a second one.
"""
import logging
import secrets
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, Query, Response
from fastapi.responses import RedirectResponse
from sqlmodel import Session, func, select

from app.config import settings
from app.database import get_session
from app.models import User
from app.routers.auth import create_user
from app.security import create_access_token, decode_subject
from app.services.google_oauth import (
    GoogleOAuthError,
    build_login_authorize_url,
    exchange_login_code,
    fetch_userinfo,
)

router = APIRouter(prefix="/auth/google", tags=["auth"])
logger = logging.getLogger("signal.auth")

STATE_TTL = timedelta(minutes=10)
STATE_COOKIE = "signal_oauth_state"


def _login_url(fragment: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/login#{fragment}"


def _fail(message: str) -> RedirectResponse:
    response = RedirectResponse(_login_url(f"error={quote(message)}"))
    response.delete_cookie(STATE_COOKIE, path="/auth/google")
    return response


@router.get("/start")
def start(response: Response):
    """Send the browser to Google. The nonce is in both the signed `state` and a
    cookie on this API's own origin; Google hands back the state and the browser
    hands back the cookie, and they have to match. Without that pairing, anyone
    could feed a victim a callback URL and sign them into someone else's
    account."""
    try:
        nonce = secrets.token_urlsafe(24)
        url = build_login_authorize_url(create_access_token(subject=nonce, expires_delta=STATE_TTL))
    except GoogleOAuthError as exc:
        return _fail(str(exc))

    redirect = RedirectResponse(url)
    redirect.set_cookie(
        STATE_COOKIE,
        nonce,
        max_age=int(STATE_TTL.total_seconds()),
        httponly=True,
        secure=settings.google_login_redirect_uri.startswith("https://"),
        samesite="lax",  # still sent on the top-level GET Google redirects back with
        path="/auth/google",
    )
    return redirect


@router.get("/callback")
def callback(
    session: Session = Depends(get_session),
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    signal_oauth_state: str = Cookie(default=""),
):
    if error:
        # The usual one is access_denied - they pressed Cancel.
        return _fail("Sign-in was cancelled.")
    if not code or not state:
        return _fail("That sign-in link was incomplete. Try again.")

    nonce = decode_subject(state)
    if nonce is None or not signal_oauth_state or not secrets.compare_digest(nonce, signal_oauth_state):
        return _fail("That sign-in request expired or came from somewhere else. Try again.")

    try:
        tokens = exchange_login_code(code)
        profile = fetch_userinfo(tokens.get("access_token", ""))
    except GoogleOAuthError as exc:
        logger.warning("Google sign-in failed: %s", exc)
        return _fail(str(exc))

    email = (profile.get("email") or "").strip().lower()
    if not email:
        return _fail("Google didn't share an email address for that account.")
    if not profile.get("email_verified"):
        # Otherwise anyone who can claim an unverified address at their own
        # Google Workspace domain could walk into an existing Signal account.
        return _fail("That Google account's email address isn't verified.")

    user = session.exec(select(User).where(func.lower(User.email) == email)).first()
    if user is None:
        user = create_user(session, email, hashed_password="")  # Google-only: no password to verify

    token = create_access_token(subject=user.email)
    redirect = RedirectResponse(_login_url(f"token={quote(token)}"))
    redirect.delete_cookie(STATE_COOKIE, path="/auth/google")
    return redirect

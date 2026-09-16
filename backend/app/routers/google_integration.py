"""Connect/disconnect a Google account and see what it gives access to.
See app/services/google_oauth.py for why this can't be fully exercised
without a real registered Google OAuth client and a human completing the
consent screen.
"""
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas import GAPropertyOption, GoogleAuthorizeResponse, GoogleConnectionStatus
from app.security import create_access_token, decode_subject
from app.services import ga, gsc
from app.services.ga import GAError
from app.services.google_connection import disconnect, get_connection, get_valid_access_token, save_connection
from app.services.google_oauth import GoogleOAuthError, build_authorize_url, exchange_code
from app.services.gsc import GSCError

router = APIRouter(prefix="/integrations/google", tags=["google-integration"])

STATE_TTL = timedelta(minutes=10)


@router.post("/connect", response_model=GoogleAuthorizeResponse)
def connect(current_user: User = Depends(get_current_user)):
    # The browser navigates the user's whole tab to Google, so this can't be
    # an ordinary Bearer-authenticated call - the frontend calls this first
    # (authenticated as normal) to get a URL, then does the navigation
    # itself. `state` re-identifies the user when Google redirects back.
    state = create_access_token(subject=current_user.email, expires_delta=STATE_TTL)
    try:
        url = build_authorize_url(state)
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return GoogleAuthorizeResponse(authorize_url=url)


@router.get("/callback")
def callback(code: str = Query(...), state: str = Query(...), session: Session = Depends(get_session)):
    email = decode_subject(state)
    if email is None:
        return RedirectResponse(
            f"{settings.frontend_url}/dashboard/settings?google_error="
            + quote("That connection request expired - try again.")
        )

    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        return RedirectResponse(
            f"{settings.frontend_url}/dashboard/settings?google_error=" + quote("User not found.")
        )

    try:
        token_data = exchange_code(code)
        save_connection(session, user, token_data)
    except (GoogleOAuthError, ValueError) as exc:
        return RedirectResponse(f"{settings.frontend_url}/dashboard/settings?google_error=" + quote(str(exc)))

    return RedirectResponse(f"{settings.frontend_url}/dashboard/settings?google=connected")


@router.get("/status", response_model=GoogleConnectionStatus)
def connection_status(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    connection = get_connection(session, current_user.id)
    if connection is None:
        return GoogleConnectionStatus(connected=False)

    try:
        access_token = get_valid_access_token(session, connection)
    except GoogleOAuthError:
        # The refresh token itself is no longer valid (revoked from Google's
        # side, most likely) - report as disconnected rather than erroring,
        # since from the user's perspective there's effectively no connection.
        return GoogleConnectionStatus(connected=False)

    try:
        gsc_properties = gsc.list_properties(access_token)
    except GSCError:
        gsc_properties = []
    try:
        ga_properties = [GAPropertyOption(**p) for p in ga.list_properties(access_token)]
    except GAError:
        ga_properties = []

    return GoogleConnectionStatus(
        connected=True,
        connected_at=connection.connected_at,
        gsc_properties=gsc_properties,
        ga_properties=ga_properties,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_google(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    disconnect(session, current_user.id)

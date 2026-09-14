"""Persist and refresh a user's Google OAuth grant (GoogleConnection row).
Split from google_oauth.py so that module stays pure-HTTP / DB-free and
easy to test in isolation - this module is the DB-touching layer on top.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.models import GoogleConnection, User
from app.services.google_oauth import refresh_access_token
from app.services.token_crypto import decrypt_token, encrypt_token

# Refresh a bit before actual expiry so a request never races an
# almost-expired token.
EXPIRY_SAFETY_MARGIN = timedelta(seconds=60)


def get_connection(session: Session, user_id: int) -> Optional[GoogleConnection]:
    return session.exec(select(GoogleConnection).where(GoogleConnection.user_id == user_id)).first()


def save_connection(session: Session, user: User, token_data: dict) -> GoogleConnection:
    """token_data is the raw response from google_oauth.exchange_code()."""
    refresh_token = token_data.get("refresh_token")
    existing = get_connection(session, user.id)

    if existing is None:
        if not refresh_token:
            # Shouldn't happen with prompt=consent, but a stale consent or a
            # Google-side quirk could omit it - without one we can't keep
            # the connection alive past the first access token's ~1hr life.
            raise ValueError("Google did not return a refresh token - try connecting again.")
        existing = GoogleConnection(user_id=user.id, refresh_token_encrypted=encrypt_token(refresh_token))
    elif refresh_token:
        existing.refresh_token_encrypted = encrypt_token(refresh_token)

    existing.access_token_encrypted = encrypt_token(token_data["access_token"])
    existing.token_expires_at = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600))
    existing.scope = token_data.get("scope", "")
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


def get_valid_access_token(session: Session, connection: GoogleConnection) -> str:
    """Returns a usable access token, transparently refreshing (and
    persisting the refresh) if the current one is at or past expiry."""
    if connection.token_expires_at > datetime.utcnow() + EXPIRY_SAFETY_MARGIN:
        return decrypt_token(connection.access_token_encrypted)

    data = refresh_access_token(decrypt_token(connection.refresh_token_encrypted))
    connection.access_token_encrypted = encrypt_token(data["access_token"])
    connection.token_expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return decrypt_token(connection.access_token_encrypted)


def disconnect(session: Session, user_id: int) -> bool:
    connection = get_connection(session, user_id)
    if connection is None:
        return False
    session.delete(connection)
    session.commit()
    return True

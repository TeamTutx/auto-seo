"""Encrypt credentials at rest.

A leaked Google refresh token is standing access to a user's real Search
Console/Analytics data (unlike, say, a session cookie, it doesn't expire on its
own), so GoogleConnection rows store ciphertext, not the raw token. The same
applies, and harder, to SiteWriteTarget: a WordPress application password or a
GitHub token is standing *write* access to the user's site.

Fernet key is derived from SECRET_KEY - no extra secret to provision, and it
already implies "rotate this and sessions/tokens invalidate together."
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class TokenDecryptError(Exception):
    pass


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def encrypt_token(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_token(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise TokenDecryptError("Stored credential could not be decrypted - SECRET_KEY may have changed.") from exc

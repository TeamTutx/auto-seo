"""Pick the write target for a site, if it has one.

`for_site` returning None is the normal case and not a failure: a site with no
row is a manual site, and the change is shown as an exact before/after to copy.
There is deliberately no null-object "manual target" implementing the interface
by raising on every call - that would let a caller believe it could write, and
find out only at the point of writing.
"""
import json
from typing import Optional

from sqlmodel import Session, select

from app.models import Site, SiteWriteTarget, WriteTargetKind
from app.services import token_crypto

from .base import FieldWrite, Receipt, TargetStatus, WriteTarget, WriteTargetError
from .github import GitHubTarget
from .wordpress import WordPressTarget


def build(row: SiteWriteTarget) -> WriteTarget:
    """Instantiate the target a stored row describes. Raises WriteTargetError
    rather than KeyError on a malformed config, since the caller is an HTTP
    handler and a 500 tells the user nothing."""
    config = json.loads(row.config or "{}")
    try:
        secret = token_crypto.decrypt_token(row.secret_encrypted)
    except token_crypto.TokenDecryptError as exc:
        raise WriteTargetError(
            "The stored credential for this site could not be decrypted, which happens if "
            "SECRET_KEY changed. Reconnect the site to store it again."
        ) from exc

    try:
        if row.kind == WriteTargetKind.wordpress.value:
            return WordPressTarget(
                base_url=config["base_url"],
                username=config["username"],
                app_password=secret,
                capabilities=config.get("capabilities"),
            )
        if row.kind == WriteTargetKind.github.value:
            return GitHubTarget(repo=config["repo"], token=secret, branch=config.get("branch", ""))
    except KeyError as exc:
        raise WriteTargetError(f"The stored connection for this site is missing {exc}. Reconnect it.") from exc

    raise WriteTargetError(f"Unknown write target kind {row.kind!r}.")


def row_for_site(session: Session, site_id: int) -> Optional[SiteWriteTarget]:
    return session.exec(select(SiteWriteTarget).where(SiteWriteTarget.site_id == site_id)).first()


def for_site(session: Session, site: Site) -> Optional[WriteTarget]:
    row = row_for_site(session, site.id)
    return build(row) if row is not None else None


__all__ = [
    "FieldWrite",
    "GitHubTarget",
    "Receipt",
    "TargetStatus",
    "WordPressTarget",
    "WriteTarget",
    "WriteTargetError",
    "build",
    "for_site",
    "row_for_site",
]

"""Remember what a credit bought.

AI suggestions and competitor lookups used to exist only in the browser's
memory: spend a credit, refresh the page, and the answer was gone - so seeing it
again meant paying again. Every metered result now lands here on its way out,
and the page reads them back when it loads.

One row per (page, kind, subject): these answer "what should I do now", so a
fresh answer replaces the old one rather than accumulating a history nobody
asked for.
"""
import json
from datetime import datetime
from typing import Any, List, Optional

from sqlmodel import Session, select

from app.models import GeneratedResult

# Page-scoped AI suggestions.
META_DESCRIPTION = "meta_description"
TITLE_TAG = "title_tag"
HEADING = "heading"
READABILITY = "readability"
INTERNAL_LINKS = "internal_links"
ALT_TEXT = "alt_text"
# Keyword-scoped: `subject` is the keyword.
COMPETITORS = "competitors"
KEYWORD_OPPORTUNITIES = "keyword_opportunities"
ACTION_PLAN = "action_plan"


def store(session: Session, page_id: int, kind: str, payload: Any, subject: str = "") -> GeneratedResult:
    """Save a paid result, replacing any previous one of the same kind. Does not
    commit - the caller owns the transaction, so the result and the credit it
    cost are written together or not at all."""
    existing = session.exec(
        select(GeneratedResult).where(
            GeneratedResult.page_id == page_id,
            GeneratedResult.kind == kind,
            GeneratedResult.subject == subject,
        )
    ).first()
    encoded = json.dumps(payload, default=str)

    if existing is not None:
        existing.payload = encoded
        existing.created_at = datetime.utcnow()
        session.add(existing)
        return existing

    row = GeneratedResult(page_id=page_id, kind=kind, subject=subject, payload=encoded)
    session.add(row)
    return row


def for_page(session: Session, page_id: int) -> List[GeneratedResult]:
    return session.exec(
        select(GeneratedResult).where(GeneratedResult.page_id == page_id).order_by(GeneratedResult.kind)
    ).all()


def decode(row: GeneratedResult) -> Optional[Any]:
    try:
        return json.loads(row.payload)
    except ValueError:
        return None

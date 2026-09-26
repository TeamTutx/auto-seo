"""Manual cascade deletes - the SQLModel relationships aren't configured with
ORM-level cascade, so deleting a Site/Page directly would leave orphaned rows
behind.

**Every table with a page_id or site_id has to be listed here.** Postgres
enforces the foreign keys and refuses the delete; SQLite (dev, and the whole
pytest suite) does not enforce them by default, so a missing table looks fine
locally and fails only in production, on a user pressing Delete. That is exactly
what had happened: this function covered audits, checks and keyword ranks, and
not the seven tables added by later phases - alerts, applied fixes, generated
results, keyword ideas, visibility checks and advice, and jobs - so deleting any
site that had ever been audited or crawled would have failed.

So: adding a table with a page or site foreign key means adding it below.
"""
from sqlmodel import Session, delete, select

from app.models import (
    Alert,
    AppliedFix,
    Audit,
    Check,
    GeneratedResult,
    KeywordIdea,
    KeywordRank,
    Page,
    ProposedChange,
    Site,
    SiteJob,
    SiteWriteTarget,
    VisibilityAdvice,
    VisibilityCheck,
)


def delete_page(session: Session, page_id: int, commit: bool = True) -> None:
    audit_ids = session.exec(select(Audit.id).where(Audit.page_id == page_id)).all()
    if audit_ids:
        session.exec(delete(Check).where(Check.audit_id.in_(audit_ids)))
        session.exec(delete(Audit).where(Audit.page_id == page_id))
    session.exec(delete(KeywordRank).where(KeywordRank.page_id == page_id))
    session.exec(delete(AppliedFix).where(AppliedFix.page_id == page_id))
    session.exec(delete(Alert).where(Alert.page_id == page_id))
    session.exec(delete(GeneratedResult).where(GeneratedResult.page_id == page_id))
    session.exec(delete(ProposedChange).where(ProposedChange.page_id == page_id))
    session.exec(delete(Page).where(Page.id == page_id))
    if commit:
        session.commit()


def delete_site(session: Session, site_id: int) -> None:
    page_ids = session.exec(select(Page.id).where(Page.site_id == site_id)).all()
    for page_id in page_ids:
        delete_page(session, page_id, commit=False)

    # Site-scoped rows, including the proposed changes that never belonged to a
    # page (a change about a page the advice says to publish).
    session.exec(delete(ProposedChange).where(ProposedChange.site_id == site_id))
    session.exec(delete(SiteWriteTarget).where(SiteWriteTarget.site_id == site_id))
    session.exec(delete(KeywordIdea).where(KeywordIdea.site_id == site_id))
    session.exec(delete(VisibilityCheck).where(VisibilityCheck.site_id == site_id))
    session.exec(delete(VisibilityAdvice).where(VisibilityAdvice.site_id == site_id))
    session.exec(delete(SiteJob).where(SiteJob.site_id == site_id))
    session.exec(delete(Site).where(Site.id == site_id))
    session.commit()

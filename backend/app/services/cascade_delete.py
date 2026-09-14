"""Manual cascade deletes - the SQLModel relationships aren't configured
with ORM-level cascade, so deleting a Site/Page directly would leave
orphaned Audit/Check/KeywordRank rows behind.
"""
from sqlmodel import Session, delete, select

from app.models import Audit, Check, KeywordRank, Page, Site


def delete_page(session: Session, page_id: int, commit: bool = True) -> None:
    audit_ids = session.exec(select(Audit.id).where(Audit.page_id == page_id)).all()
    if audit_ids:
        session.exec(delete(Check).where(Check.audit_id.in_(audit_ids)))
        session.exec(delete(Audit).where(Audit.page_id == page_id))
    session.exec(delete(KeywordRank).where(KeywordRank.page_id == page_id))
    session.exec(delete(Page).where(Page.id == page_id))
    if commit:
        session.commit()


def delete_site(session: Session, site_id: int) -> None:
    page_ids = session.exec(select(Page.id).where(Page.site_id == site_id)).all()
    for page_id in page_ids:
        delete_page(session, page_id, commit=False)
    session.exec(delete(Site).where(Site.id == site_id))
    session.commit()

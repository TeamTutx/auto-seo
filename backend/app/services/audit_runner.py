from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import Audit, Check, Page, Site
from app.services.applied_fixes import verify_applied_fixes_for_audit
from app.services.audit_engine import run_onpage_audit
from app.services.fetcher import fetch_html


def _sibling_titles(session: Session, site_id: int, exclude_page_id: int) -> list:
    other_page_ids = session.exec(
        select(Page.id).where(Page.site_id == site_id, Page.id != exclude_page_id)
    ).all()
    if not other_page_ids:
        return []
    latest_titles = session.exec(
        select(Audit.extracted_title)
        .where(Audit.page_id.in_(other_page_ids), Audit.extracted_title.is_not(None))
    ).all()
    return [t for t in latest_titles if t]


def audit_page(session: Session, page_id: int) -> Audit:
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    try:
        html = fetch_html(page.url)
    except Exception as exc:  # httpx raises several distinct error types here
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch page: {exc}",
        )

    sibling_titles = _sibling_titles(session, page.site_id, page.id)
    result = run_onpage_audit(html, page.url, page.target_keyword, sibling_titles)

    audit = Audit(
        page_id=page.id,
        score=result.score,
        extracted_title=result.extracted_title,
        word_count=result.word_count,
    )
    session.add(audit)
    session.flush()  # assigns audit.id without committing, so the checks below join the same transaction

    for check in result.checks:
        session.add(Check(
            audit_id=audit.id,
            check_type=check.check_type,
            status=check.status,
            message=check.message,
            suggested_fix=check.suggested_fix,
        ))
    # One commit for the audit and all its checks: if a check insert fails, the
    # audit row rolls back with it instead of being left behind as a score with
    # an empty checklist (which also used up the free plan's daily rescan).
    session.commit()
    session.refresh(audit)

    site = session.get(Site, page.site_id)
    if site is not None:
        verify_applied_fixes_for_audit(session, site.user_id, page, audit)

    return audit

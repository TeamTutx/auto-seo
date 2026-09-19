"""Scheduled automated re-audits + alerts (REQUIREMENTS.md §2.7). This used to
be a Pro/Agency perk; Signal is credit-based now, so it runs for every account.
Email delivery needs a Resend/SendGrid key we don't have, so alerts land in-app
(Alert rows) instead - see app/routers/alerts.py.

Still not provisioned in production: nothing calls this on a schedule yet (see
plan.md "Not yet scheduled"), which is why the landing page doesn't claim it.
"""
from typing import List, Optional

from sqlmodel import Session, select

from app.models import Alert, AlertType, Audit, Check, CheckStatus, Page, Site, User
from app.services.audit_runner import audit_page

SCORE_DROP_THRESHOLD = 10


def _create_alerts_for_audit(
    session: Session,
    user_id: int,
    page: Page,
    new_audit: Audit,
    previous_audit: Optional[Audit],
) -> List[Alert]:
    alerts: List[Alert] = []

    if previous_audit and previous_audit.score is not None and new_audit.score is not None:
        drop = previous_audit.score - new_audit.score
        if drop >= SCORE_DROP_THRESHOLD:
            alerts.append(Alert(
                user_id=user_id,
                page_id=page.id,
                alert_type=AlertType.score_drop,
                message=f"{page.url} score dropped from {previous_audit.score} to {new_audit.score} ({drop} points).",
            ))

    previously_failed = set()
    if previous_audit:
        previously_failed = {
            c.check_type
            for c in session.exec(
                select(Check).where(Check.audit_id == previous_audit.id, Check.status == CheckStatus.fail)
            ).all()
        }

    new_failed_checks = session.exec(
        select(Check).where(Check.audit_id == new_audit.id, Check.status == CheckStatus.fail)
    ).all()
    newly_failed = [c for c in new_failed_checks if c.check_type not in previously_failed]
    if newly_failed:
        names = ", ".join(c.check_type for c in newly_failed)
        alerts.append(Alert(
            user_id=user_id,
            page_id=page.id,
            alert_type=AlertType.new_fail,
            message=f"{page.url} now fails: {names}.",
        ))

    for alert in alerts:
        session.add(alert)
    if alerts:
        session.commit()
    return alerts


def run_scheduled_audits(session: Session) -> int:
    """Re-audit every tracked page; raise an Alert on a meaningful regression
    (score drop or a newly-failing check). Returns the number of alerts created.
    A single page's fetch failure doesn't abort the rest of the run."""
    page_ids = session.exec(
        select(Page.id)
        .join(Site, Site.id == Page.site_id)
        .join(User, User.id == Site.user_id)
    ).all()

    alert_count = 0
    for page_id in page_ids:
        page = session.get(Page, page_id)
        if page is None:
            continue
        site = session.get(Site, page.site_id)
        if site is None:
            continue

        previous_audit = session.exec(
            select(Audit).where(Audit.page_id == page_id).order_by(Audit.created_at.desc())
        ).first()

        try:
            new_audit = audit_page(session, page_id)
        except Exception:
            continue

        alerts = _create_alerts_for_audit(session, site.user_id, page, new_audit, previous_audit)
        alert_count += len(alerts)

    return alert_count

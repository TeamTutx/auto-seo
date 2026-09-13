"""Async wrapper around the audit engine (REQUIREMENTS.md: Celery + Redis for slow jobs).

Not wired into the API yet — audits currently run inline in the request
(see app/routers/audits.py) since a single page fetch+parse is fast enough
for the MVP. Swap the inline call for `run_page_audit.delay(page_id)` once
audits start covering multi-page crawls or need to be queued.
"""
from app.workers.celery_app import celery_app


@celery_app.task(name="run_page_audit")
def run_page_audit(page_id: int) -> int:
    from sqlmodel import Session

    from app.database import engine
    from app.services.audit_runner import audit_page

    with Session(engine) as session:
        audit = audit_page(session, page_id)
        return audit.id

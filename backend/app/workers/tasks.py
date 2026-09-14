"""Celery tasks. REQUIREMENTS.md: Celery + Redis for slow jobs.

run_page_audit: not wired into the API yet - audits currently run inline in
the request (see app/routers/audits.py) since a single page fetch+parse is
fast enough for the MVP. Swap the inline call for run_page_audit.delay(page_id)
once audits start covering multi-page crawls or need to be queued.

run_scheduled_audits: the actual consumer of Celery Beat (see celery_app.py's
beat_schedule) - re-audits every Pro/Agency page daily and raises in-app
Alerts on a regression. This one IS live: requires a running worker
(`celery -A app.workers.celery_app worker`) and beat process
(`celery -A app.workers.celery_app beat`), both needing Redis.
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


@celery_app.task(name="run_scheduled_audits")
def run_scheduled_audits_task() -> int:
    from sqlmodel import Session

    from app.database import engine
    from app.services.scheduled_audits import run_scheduled_audits

    with Session(engine) as session:
        return run_scheduled_audits(session)

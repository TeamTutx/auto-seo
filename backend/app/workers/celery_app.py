from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "signal",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.beat_schedule = {
    "run-scheduled-audits-daily": {
        "task": "run_scheduled_audits",
        "schedule": crontab(hour=3, minute=0),  # 3am UTC - low-traffic hours
    },
}

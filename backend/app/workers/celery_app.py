from celery import Celery

from app.config import settings

celery_app = Celery(
    "signal",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

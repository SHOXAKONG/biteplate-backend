from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "biteplate",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.notifications", "app.tasks.scheduled"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="biteplate.default",
    task_routes={
        "app.tasks.notifications.send_sms": {"queue": "sms.send"},
        "app.tasks.scheduled.send_reservation_reminder": {"queue": "sms.send"},
    },
    task_default_retry_delay=30,
    task_max_retries=5,
)

celery_app.conf.beat_schedule = {
    "rotate-history-snapshot": {
        "task": "app.tasks.scheduled.rotate_history_snapshot",
        "schedule": crontab(hour=3, minute=0),
    },
}

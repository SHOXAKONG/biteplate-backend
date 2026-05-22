import structlog
from celery.exceptions import MaxRetriesExceededError

from app.celery_app import celery_app
from app.services.sms import sms_client

log = structlog.get_logger()


@celery_app.task(
    name="app.tasks.notifications.send_sms",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def send_sms(self, to: str, body: str) -> dict:
    try:
        result = sms_client.send(to, body)
        log.info("sms_sent", to=to, status=result.get("status"))
        return result
    except MaxRetriesExceededError:
        log.error("sms_send_max_retries_exceeded", to=to)
        raise

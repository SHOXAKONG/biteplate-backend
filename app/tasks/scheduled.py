import uuid

import structlog
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.config import settings
from app.models.reservation import Reservation
from app.services.sms import sms_client

log = structlog.get_logger()

_sync_engine = create_engine(settings.SYNC_DATABASE_URL, pool_pre_ping=True, future=True)
_SyncSession = sessionmaker(_sync_engine, expire_on_commit=False)


@celery_app.task(
    name="app.tasks.scheduled.send_reservation_reminder",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_reservation_reminder(self, reservation_id: str) -> dict:
    with _SyncSession() as session:
        reservation = session.execute(
            select(Reservation).where(Reservation.id == uuid.UUID(reservation_id))
        ).scalar_one_or_none()

        if reservation is None or reservation.status == "cancelled":
            log.info("reminder_skipped", reservation_id=reservation_id)
            return {"status": "skipped"}

        body = (
            f"Reminder: Hi {reservation.customer_name}, your table is booked at "
            f"{reservation.booking_time.strftime('%H:%M on %Y-%m-%d')} for "
            f"{reservation.party_size} people."
        )
        return sms_client.send(reservation.customer_phone, body)


@celery_app.task(name="app.tasks.scheduled.rotate_history_snapshot")
def rotate_history_snapshot() -> dict:
    from app.services.history import order_history

    return {"history_size": order_history.size()}

"""Notifications: Observer pattern. One observer crosses into Celery for SMS."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class OrderEvent:
    kind: str
    order_id: str
    table_id: str | None = None
    total: float | None = None
    customer_phone: str | None = None
    customer_name: str | None = None
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = field(default_factory=dict)


class OrderObserver(ABC):
    @abstractmethod
    def update(self, event: OrderEvent) -> None: ...


class OrderSubject:
    def __init__(self):
        self._observers: list[OrderObserver] = []
        self._lock = threading.RLock()

    def attach(self, observer: OrderObserver) -> None:
        with self._lock:
            if observer not in self._observers:
                self._observers.append(observer)

    def detach(self, observer: OrderObserver) -> None:
        with self._lock:
            if observer in self._observers:
                self._observers.remove(observer)

    def notify(self, event: OrderEvent) -> None:
        with self._lock:
            observers = list(self._observers)
        for observer in observers:
            try:
                observer.update(event)
            except Exception as exc:
                log.exception("observer_failed", observer=type(observer).__name__, error=str(exc))


order_subject = OrderSubject()


class KitchenDisplayObserver(OrderObserver):
    def update(self, event: OrderEvent) -> None:
        if event.kind in ("order_placed", "order_cancelled"):
            log.info("kitchen_display_update", event=event.kind, order_id=event.order_id)


class WaiterDashboardObserver(OrderObserver):
    def update(self, event: OrderEvent) -> None:
        log.info("waiter_dashboard_update", event=event.kind, order_id=event.order_id)


class ManagerDashboardObserver(OrderObserver):
    def update(self, event: OrderEvent) -> None:
        if event.kind == "order_placed" and event.total is not None:
            log.info(
                "manager_dashboard_update",
                event=event.kind,
                order_id=event.order_id,
                total=event.total,
            )


class AllergenAlerterObserver(OrderObserver):
    def update(self, event: OrderEvent) -> None:
        allergens = event.payload.get("allergens") or []
        if allergens:
            log.warning(
                "allergen_alert", order_id=event.order_id, allergens=allergens
            )


class HistorySinkObserver(OrderObserver):
    def update(self, event: OrderEvent) -> None:
        if event.kind != "order_confirmed":
            return
        from app.services.history import HistoryEntry, order_history

        entry = HistoryEntry(
            order_id=event.order_id,
            table_id=event.table_id or "",
            placed_at=event.occurred_at,
            total=event.total or 0.0,
            items=event.payload.get("items", []),
        )
        order_history.append(entry)


class SmsNotificationObserver(OrderObserver):
    def update(self, event: OrderEvent) -> None:
        if event.kind not in ("reservation_confirmed", "order_ready"):
            return
        if not event.customer_phone:
            return
        from app.tasks.notifications import send_sms

        body = self._build_message(event)
        send_sms.delay(event.customer_phone, body)

    @staticmethod
    def _build_message(event: OrderEvent) -> str:
        if event.kind == "reservation_confirmed":
            return (
                f"Hi {event.customer_name or 'guest'}, your reservation is confirmed "
                f"({event.payload.get('booking_time', '')})."
            )
        return f"Your order #{event.order_id[:8]} is ready."


def register_default_observers() -> None:
    for observer in [
        KitchenDisplayObserver(),
        WaiterDashboardObserver(),
        ManagerDashboardObserver(),
        AllergenAlerterObserver(),
        HistorySinkObserver(),
        SmsNotificationObserver(),
    ]:
        order_subject.attach(observer)

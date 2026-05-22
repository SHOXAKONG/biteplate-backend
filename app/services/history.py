"""History domain: Singleton + Iterator."""
from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime

from app.models.order import Order


@dataclass
class HistoryEntry:
    order_id: str
    table_id: str
    placed_at: datetime
    total: float
    items: list[dict] = field(default_factory=list)


class _OrderHistoryRepository:
    """Singleton: every confirmed order is appended via the Observer chain."""

    _instance: "_OrderHistoryRepository | None" = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._entries = []  # type: ignore[attr-defined]
                cls._instance._entries_lock = threading.RLock()  # type: ignore[attr-defined]
        return cls._instance

    def append(self, entry: HistoryEntry) -> None:
        with self._entries_lock:
            self._entries.append(entry)

    def append_from_order(self, order: Order) -> None:
        entry = HistoryEntry(
            order_id=str(order.id),
            table_id=str(order.table_id),
            placed_at=order.created_at or datetime.utcnow(),
            total=float(order.total or 0),
            items=[
                {
                    "name": i.menu_item_name,
                    "quantity": i.quantity,
                    "unit_price": float(i.unit_price),
                }
                for i in (order.items or [])
            ],
        )
        self.append(entry)

    def all_entries(self) -> list[HistoryEntry]:
        with self._entries_lock:
            return list(self._entries)

    def size(self) -> int:
        return len(self._entries)


order_history = _OrderHistoryRepository()


# ---------- Iterator pattern ----------

class DateRangeIterator(Iterator[HistoryEntry]):
    def __init__(self, repo: _OrderHistoryRepository, start: datetime, end: datetime):
        self._entries = [e for e in repo.all_entries() if start <= e.placed_at < end]
        self._index = 0

    def __iter__(self) -> "DateRangeIterator":
        return self

    def __next__(self) -> HistoryEntry:
        if self._index >= len(self._entries):
            raise StopIteration
        entry = self._entries[self._index]
        self._index += 1
        return entry


class TableHistoryIterator(Iterator[HistoryEntry]):
    def __init__(self, repo: _OrderHistoryRepository, table_id: uuid.UUID):
        self._entries = [e for e in repo.all_entries() if e.table_id == str(table_id)]
        self._index = 0

    def __iter__(self) -> "TableHistoryIterator":
        return self

    def __next__(self) -> HistoryEntry:
        if self._index >= len(self._entries):
            raise StopIteration
        entry = self._entries[self._index]
        self._index += 1
        return entry


class TopItemsIterator(Iterator[dict]):
    def __init__(self, repo: _OrderHistoryRepository, limit: int = 10):
        aggregates: dict[str, dict] = {}
        for entry in repo.all_entries():
            for item in entry.items:
                bucket = aggregates.setdefault(
                    item["name"], {"name": item["name"], "times_ordered": 0, "revenue": 0.0}
                )
                bucket["times_ordered"] += item["quantity"]
                bucket["revenue"] += item["unit_price"] * item["quantity"]
        ranked = sorted(aggregates.values(), key=lambda b: b["times_ordered"], reverse=True)
        self._entries = ranked[:limit]
        self._index = 0

    def __iter__(self) -> "TopItemsIterator":
        return self

    def __next__(self) -> dict:
        if self._index >= len(self._entries):
            raise StopIteration
        entry = self._entries[self._index]
        self._index += 1
        return entry

"""Kitchen domain: Command pattern with an in-process invoker queue."""
from __future__ import annotations

import threading
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from app.core.exceptions import ConflictError, NotFoundError


@dataclass
class TicketSnapshot:
    order_id: str
    status: str
    enqueued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict = field(default_factory=dict)


class Command(ABC):
    @abstractmethod
    def execute(self, queue: "KitchenQueue") -> None: ...

    @abstractmethod
    def undo(self, queue: "KitchenQueue") -> None: ...

    @abstractmethod
    def describe(self) -> dict: ...


class PrepareOrderCommand(Command):
    def __init__(self, order_id: uuid.UUID, station: str = "default"):
        self.order_id = order_id
        self.station = station
        self._snapshot: TicketSnapshot | None = None

    def execute(self, queue: KitchenQueue) -> None:
        snapshot = TicketSnapshot(
            order_id=str(self.order_id),
            status="pending",
            enqueued_at=datetime.utcnow(),
            metadata={"station": self.station},
        )
        queue._enqueue(snapshot)
        self._snapshot = snapshot

    def undo(self, queue: KitchenQueue) -> None:
        if self._snapshot:
            queue._remove(self._snapshot)

    def describe(self) -> dict:
        return {"kind": "prepare", "order_id": str(self.order_id), "station": self.station}


class ExpediteOrderCommand(Command):
    def __init__(self, order_id: uuid.UUID):
        self.order_id = order_id
        self._previous_position: int | None = None

    def execute(self, queue: KitchenQueue) -> None:
        self._previous_position = queue._move_to_front(self.order_id)

    def undo(self, queue: KitchenQueue) -> None:
        if self._previous_position is not None:
            queue._restore_position(self.order_id, self._previous_position)

    def describe(self) -> dict:
        return {"kind": "expedite", "order_id": str(self.order_id)}


class CancelOrderCommand(Command):
    def __init__(self, order_id: uuid.UUID):
        self.order_id = order_id
        self._snapshot: TicketSnapshot | None = None
        self._was_waste: bool = False

    def execute(self, queue: KitchenQueue) -> None:
        self._snapshot = queue._find(self.order_id)
        if self._snapshot is None:
            raise NotFoundError(f"No kitchen ticket for order {self.order_id}")
        self._was_waste = self._snapshot.status == "in_progress"
        queue._remove(self._snapshot)
        if self._was_waste:
            queue.waste_count += 1

    def undo(self, queue: KitchenQueue) -> None:
        if self._snapshot:
            queue._enqueue(self._snapshot)
            if self._was_waste:
                queue.waste_count -= 1

    def describe(self) -> dict:
        return {"kind": "cancel", "order_id": str(self.order_id)}


class KitchenQueue:
    def __init__(self):
        self._pending: deque[TicketSnapshot] = deque()
        self._in_progress: list[TicketSnapshot] = []
        self._completed: list[TicketSnapshot] = []
        self._history: list[Command] = []
        self._lock = threading.RLock()
        self.waste_count: int = 0

    def submit(self, command: Command) -> None:
        with self._lock:
            command.execute(self)
            self._history.append(command)

    def undo_last(self) -> Command | None:
        with self._lock:
            if not self._history:
                return None
            command = self._history.pop()
            command.undo(self)
            return command

    def start_next(self) -> TicketSnapshot | None:
        with self._lock:
            if not self._pending:
                return None
            ticket = self._pending.popleft()
            ticket.status = "in_progress"
            ticket.started_at = datetime.utcnow()
            self._in_progress.append(ticket)
            return ticket

    def complete(self, order_id: uuid.UUID) -> TicketSnapshot:
        with self._lock:
            for ticket in list(self._in_progress):
                if ticket.order_id == str(order_id):
                    ticket.status = "completed"
                    ticket.completed_at = datetime.utcnow()
                    self._in_progress.remove(ticket)
                    self._completed.append(ticket)
                    return ticket
            raise NotFoundError(f"No in-progress ticket for order {order_id}")

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "pending": [t.__dict__ for t in self._pending],
                "in_progress": [t.__dict__ for t in self._in_progress],
                "completed": [t.__dict__ for t in self._completed[-20:]],
                "history_size": len(self._history),
            }

    def _enqueue(self, ticket: TicketSnapshot) -> None:
        self._pending.append(ticket)

    def _remove(self, ticket: TicketSnapshot) -> None:
        if ticket in self._pending:
            self._pending.remove(ticket)
        elif ticket in self._in_progress:
            self._in_progress.remove(ticket)

    def _find(self, order_id: uuid.UUID) -> TicketSnapshot | None:
        for t in list(self._pending) + self._in_progress:
            if t.order_id == str(order_id):
                return t
        return None

    def _move_to_front(self, order_id: uuid.UUID) -> int | None:
        for index, ticket in enumerate(self._pending):
            if ticket.order_id == str(order_id):
                self._pending.remove(ticket)
                self._pending.appendleft(ticket)
                return index
        raise ConflictError(f"Order {order_id} is not pending")

    def _restore_position(self, order_id: uuid.UUID, position: int) -> None:
        target = next((t for t in self._pending if t.order_id == str(order_id)), None)
        if target is None:
            return
        self._pending.remove(target)
        items = list(self._pending)
        items.insert(position, target)
        self._pending = deque(items)


kitchen_queue = KitchenQueue()

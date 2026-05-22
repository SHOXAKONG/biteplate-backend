"""Table domain: State pattern."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidStateTransition, NotFoundError
from app.dto.tables import TableCreateDTO, TableDTO
from app.models.table import TableModel
from app.repositories.table import TableRepository


class TableState(ABC):
    name: str = "abstract"

    @abstractmethod
    def reserve(self, ctx: "TableContext") -> None: ...

    @abstractmethod
    def seat(self, ctx: "TableContext") -> None: ...

    @abstractmethod
    def attach_order(self, ctx: "TableContext", order_id: str) -> None: ...

    @abstractmethod
    def request_bill(self, ctx: "TableContext") -> None: ...

    @abstractmethod
    def clear(self, ctx: "TableContext") -> None: ...

    @abstractmethod
    def free(self, ctx: "TableContext") -> None: ...

    def _illegal(self, action: str) -> None:
        raise InvalidStateTransition(f"Cannot {action} a table in '{self.name}' state")


class FreeState(TableState):
    name = "free"

    def reserve(self, ctx): ctx.set_state(ReservedState())
    def seat(self, ctx): ctx.set_state(OccupiedState())
    def attach_order(self, ctx, order_id): self._illegal("attach_order")
    def request_bill(self, ctx): self._illegal("request_bill")
    def clear(self, ctx): self._illegal("clear")
    def free(self, ctx): pass


class ReservedState(TableState):
    name = "reserved"

    def reserve(self, ctx): self._illegal("reserve")
    def seat(self, ctx): ctx.set_state(OccupiedState())
    def attach_order(self, ctx, order_id): self._illegal("attach_order")
    def request_bill(self, ctx): self._illegal("request_bill")
    def clear(self, ctx): self._illegal("clear")
    def free(self, ctx): ctx.set_state(FreeState())


class OccupiedState(TableState):
    name = "occupied"

    def reserve(self, ctx): self._illegal("reserve")
    def seat(self, ctx): self._illegal("seat")

    def attach_order(self, ctx, order_id):
        ctx.model.current_order_id = order_id

    def request_bill(self, ctx): ctx.set_state(AwaitingBillState())
    def clear(self, ctx): self._illegal("clear")
    def free(self, ctx): self._illegal("free")


class AwaitingBillState(TableState):
    name = "awaiting_bill"

    def reserve(self, ctx): self._illegal("reserve")
    def seat(self, ctx): self._illegal("seat")
    def attach_order(self, ctx, order_id): self._illegal("attach_order")
    def request_bill(self, ctx): self._illegal("request_bill")

    def clear(self, ctx):
        ctx.model.current_order_id = None
        ctx.set_state(ClearedState())

    def free(self, ctx): self._illegal("free")


class ClearedState(TableState):
    name = "cleared"

    def reserve(self, ctx): self._illegal("reserve")
    def seat(self, ctx): self._illegal("seat")
    def attach_order(self, ctx, order_id): self._illegal("attach_order")
    def request_bill(self, ctx): self._illegal("request_bill")
    def clear(self, ctx): self._illegal("clear")

    def free(self, ctx): ctx.set_state(FreeState())


_STATE_BY_NAME: dict[str, type[TableState]] = {
    s.name: s
    for s in [FreeState, ReservedState, OccupiedState, AwaitingBillState, ClearedState]
}


class TableContext:
    def __init__(self, model: TableModel):
        self.model = model
        cls = _STATE_BY_NAME.get(model.status, FreeState)
        self._state: TableState = cls()

    @property
    def state(self) -> TableState:
        return self._state

    def set_state(self, state: TableState) -> None:
        self._state = state
        self.model.status = state.name

    def apply(self, action: str, **kwargs) -> None:
        method = getattr(self._state, action, None)
        if method is None:
            raise InvalidStateTransition(f"Unknown action: {action}")
        method(self, **kwargs)


class TableService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = TableRepository(session)

    async def create(self, dto: TableCreateDTO) -> TableDTO:
        model = TableModel(number=dto.number, seats=dto.seats, status=FreeState.name)
        await self.repo.add(model)
        return TableDTO.model_validate(model)

    async def list_all(self) -> list[TableDTO]:
        return [TableDTO.model_validate(m) for m in await self.repo.list_all()]

    async def perform_action(self, table_id: uuid.UUID, action: str) -> TableDTO:
        model = await self.repo.get(table_id)
        if model is None:
            raise NotFoundError(f"Table {table_id} not found")
        ctx = TableContext(model)
        ctx.apply(action)
        await self.session.flush()
        return TableDTO.model_validate(model)

    async def update(self, table_id: uuid.UUID, number: int | None, seats: int | None) -> TableDTO:
        model = await self.repo.get(table_id)
        if model is None:
            raise NotFoundError(f"Table {table_id} not found")
        if number is not None:
            model.number = number
        if seats is not None:
            model.seats = seats
        await self.session.flush()
        return TableDTO.model_validate(model)

    async def delete(self, table_id: uuid.UUID) -> None:
        model = await self.repo.get(table_id)
        if model is None:
            raise NotFoundError(f"Table {table_id} not found")
        await self.repo.delete(model)

    async def attach_order(self, table_id: uuid.UUID, order_id: uuid.UUID) -> None:
        model = await self.repo.get(table_id)
        if model is None:
            raise NotFoundError(f"Table {table_id} not found")
        ctx = TableContext(model)
        if isinstance(ctx.state, FreeState | ReservedState):
            ctx.apply("seat")
        ctx.apply("attach_order", order_id=str(order_id))
        await self.session.flush()

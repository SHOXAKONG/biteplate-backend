import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.dependencies import require_role
from app.dto.history import HistoryEntryDTO, TopItemDTO
from app.services.history import (
    DateRangeIterator,
    TableHistoryIterator,
    TopItemsIterator,
    order_history,
)

router = APIRouter()


@router.get(
    "",
    response_model=list[HistoryEntryDTO],
    dependencies=[Depends(require_role("manager", "cashier"))],
)
async def in_range(
    start: datetime = Query(...),
    end: datetime = Query(...),
):
    iterator = DateRangeIterator(order_history, start, end)
    return [HistoryEntryDTO(**entry.__dict__) for entry in iterator]


@router.get(
    "/by-table/{table_id}",
    response_model=list[HistoryEntryDTO],
    dependencies=[Depends(require_role("manager"))],
)
async def by_table(table_id: uuid.UUID):
    iterator = TableHistoryIterator(order_history, table_id)
    return [HistoryEntryDTO(**entry.__dict__) for entry in iterator]


@router.get(
    "/top-items",
    response_model=list[TopItemDTO],
    dependencies=[Depends(require_role("manager"))],
)
async def top_items(limit: int = Query(10, ge=1, le=100)):
    iterator = TopItemsIterator(order_history, limit=limit)
    return [TopItemDTO(**entry) for entry in iterator]

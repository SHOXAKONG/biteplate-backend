from datetime import datetime

from pydantic import BaseModel


class HistoryEntryDTO(BaseModel):
    order_id: str
    table_id: str
    total: float
    placed_at: datetime
    items: list[dict]


class TopItemDTO(BaseModel):
    name: str
    times_ordered: int
    revenue: float

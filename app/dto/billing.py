import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BillRequestDTO(BaseModel):
    order_id: uuid.UUID
    split_count: int = Field(default=1, ge=1, le=20)


class BillSplitDTO(BaseModel):
    index: int
    amount: float


class BillDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    subtotal: float
    tax: float
    total: float
    splits: list[dict]
    pricing_strategy: str
    status: str
    cashier_sub: str | None = None
    payment_method: str | None = None
    created_at: datetime | None = None


class BillStatusUpdateDTO(BaseModel):
    status: Literal["paid", "unpaid", "void"]
    payment_method: Literal["cash", "card", "online"] | None = None

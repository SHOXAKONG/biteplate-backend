import uuid

from pydantic import BaseModel, Field


class PricingPreviewDTO(BaseModel):
    order_id: uuid.UUID
    loyalty_tier: str | None = None
    party_size: int = Field(default=1, ge=1)


class PricingResultDTO(BaseModel):
    strategy: str
    subtotal: float
    discount: float
    total: float
    notes: list[str]

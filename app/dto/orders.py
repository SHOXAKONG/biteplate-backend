import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.dto.menu import DecoratorSpecDTO


class OrderItemCreateDTO(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int = Field(gt=0, default=1)
    decorators: list[DecoratorSpecDTO] = Field(default_factory=list)


class OrderCreateDTO(BaseModel):
    table_id: uuid.UUID
    items: list[OrderItemCreateDTO]
    notes: str | None = None


class OrderItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    menu_item_id: uuid.UUID
    menu_item_name: str
    quantity: int
    unit_price: float
    decorators: list[dict]
    status: str


class OrderDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    table_id: uuid.UUID
    waiter_sub: str
    status: str
    subtotal: float
    total: float
    pricing_strategy: str
    notes: str | None
    items: list[OrderItemDTO]

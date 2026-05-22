import uuid

from pydantic import BaseModel


class KitchenCommandDTO(BaseModel):
    kind: str
    order_id: uuid.UUID
    item_id: uuid.UUID | None = None


class KitchenStateDTO(BaseModel):
    pending: list[dict]
    in_progress: list[dict]
    completed: list[dict]
    history_size: int

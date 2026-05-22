import uuid

from pydantic import BaseModel, ConfigDict, Field


class TableCreateDTO(BaseModel):
    number: int = Field(gt=0)
    seats: int = Field(gt=0, default=4)


class TableUpdateDTO(BaseModel):
    number: int | None = Field(default=None, gt=0)
    seats: int | None = Field(default=None, gt=0)


class TableDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: int
    seats: int
    status: str
    current_order_id: str | None


class TableActionDTO(BaseModel):
    action: str

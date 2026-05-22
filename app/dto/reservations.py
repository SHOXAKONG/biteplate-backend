import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReservationCreateDTO(BaseModel):
    table_id: uuid.UUID
    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: str = Field(min_length=5, max_length=32)
    party_size: int = Field(gt=0)
    booking_time: datetime


class ReservationUpdateDTO(BaseModel):
    party_size: int | None = Field(default=None, gt=0)
    booking_time: datetime | None = None
    customer_phone: str | None = Field(default=None, min_length=5, max_length=32)


class ReservationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    table_id: uuid.UUID
    customer_sub: str
    customer_name: str
    customer_phone: str
    party_size: int
    booking_time: datetime
    status: str

import uuid

from pydantic import BaseModel, ConfigDict, Field


class MenuItemCreateDTO(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    base_price: float = Field(gt=0)
    category: str = "main"
    is_combo: bool = False
    parent_id: uuid.UUID | None = None
    allergens: list[str] = Field(default_factory=list)


class MenuItemUpdateDTO(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    base_price: float | None = Field(default=None, gt=0)
    category: str | None = None
    is_combo: bool | None = None
    parent_id: uuid.UUID | None = None
    available: bool | None = None
    allergens: list[str] | None = None


class MenuItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    base_price: float
    category: str
    is_combo: bool
    parent_id: uuid.UUID | None
    location_code: str
    available: bool
    allergens: list[str]


class DecoratorSpecDTO(BaseModel):
    kind: str
    payload: dict = Field(default_factory=dict)


class PricedMenuItemDTO(BaseModel):
    item_id: uuid.UUID
    name: str
    base_price: float
    decorated_price: float
    decorators_applied: list[str]
    allergens: list[str]
    children: list["PricedMenuItemDTO"] = Field(default_factory=list)


PricedMenuItemDTO.model_rebuild()

"""Menu domain: Composite + Decorator + Factory Method."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.dto.menu import DecoratorSpecDTO, MenuItemCreateDTO, MenuItemDTO, PricedMenuItemDTO
from app.models.menu_item import MenuItemModel
from app.repositories.menu import MenuRepository


# ---------- Composite ----------

class MenuItem(ABC):
    @property
    @abstractmethod
    def id(self) -> uuid.UUID: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def get_price(self) -> float: ...

    @abstractmethod
    def get_allergens(self) -> list[str]: ...

    @abstractmethod
    def to_kitchen_tickets(self) -> list[dict]: ...


class SimpleMenuItem(MenuItem):
    def __init__(self, model: MenuItemModel):
        self._model = model

    @property
    def id(self) -> uuid.UUID:
        return self._model.id

    @property
    def name(self) -> str:
        return self._model.name

    def get_price(self) -> float:
        return float(self._model.base_price)

    def get_allergens(self) -> list[str]:
        return list(self._model.allergens or [])

    def to_kitchen_tickets(self) -> list[dict]:
        return [{"item_id": str(self._model.id), "name": self._model.name}]


class ComboMeal(MenuItem):
    def __init__(self, model: MenuItemModel, children: list[MenuItem]):
        self._model = model
        self._children = children

    @property
    def id(self) -> uuid.UUID:
        return self._model.id

    @property
    def name(self) -> str:
        return self._model.name

    def get_price(self) -> float:
        return sum(c.get_price() for c in self._children)

    def get_allergens(self) -> list[str]:
        out: set[str] = set(self._model.allergens or [])
        for c in self._children:
            out.update(c.get_allergens())
        return sorted(out)

    def to_kitchen_tickets(self) -> list[dict]:
        tickets: list[dict] = []
        for c in self._children:
            tickets.extend(c.to_kitchen_tickets())
        return tickets

    @property
    def children(self) -> list[MenuItem]:
        return list(self._children)


# ---------- Decorator ----------

class MenuItemDecorator(MenuItem):
    kind: str = "abstract"

    def __init__(self, wrapped: MenuItem):
        self._wrapped = wrapped

    @property
    def id(self) -> uuid.UUID:
        return self._wrapped.id

    @property
    def name(self) -> str:
        return self._wrapped.name

    def get_price(self) -> float:
        return self._wrapped.get_price()

    def get_allergens(self) -> list[str]:
        return self._wrapped.get_allergens()

    def to_kitchen_tickets(self) -> list[dict]:
        return self._wrapped.to_kitchen_tickets()


class ExtraCheeseDecorator(MenuItemDecorator):
    kind = "extra_cheese"
    PRICE = 0.50

    def get_price(self) -> float:
        return self._wrapped.get_price() + self.PRICE

    def get_allergens(self) -> list[str]:
        return sorted(set(self._wrapped.get_allergens()) | {"dairy"})

    def to_kitchen_tickets(self) -> list[dict]:
        tickets = self._wrapped.to_kitchen_tickets()
        for t in tickets:
            t.setdefault("mods", []).append("+ extra cheese")
        return tickets


class AllergenFlagDecorator(MenuItemDecorator):
    kind = "allergen_flag"

    def __init__(self, wrapped: MenuItem, allergen: str):
        super().__init__(wrapped)
        self._allergen = allergen

    def to_kitchen_tickets(self) -> list[dict]:
        tickets = self._wrapped.to_kitchen_tickets()
        for t in tickets:
            t.setdefault("warnings", []).append(f"ALLERGY: {self._allergen}")
        return tickets


class SubstitutionDecorator(MenuItemDecorator):
    kind = "substitution"

    def __init__(self, wrapped: MenuItem, swap_from: str, swap_to: str, price_delta: float = 0.0):
        super().__init__(wrapped)
        self._from = swap_from
        self._to = swap_to
        self._delta = price_delta

    def get_price(self) -> float:
        return self._wrapped.get_price() + self._delta

    def to_kitchen_tickets(self) -> list[dict]:
        tickets = self._wrapped.to_kitchen_tickets()
        for t in tickets:
            t.setdefault("mods", []).append(f"swap {self._from} -> {self._to}")
        return tickets


def apply_decorators(item: MenuItem, specs: list[DecoratorSpecDTO]) -> MenuItem:
    decorated = item
    for spec in specs:
        if spec.kind == "extra_cheese":
            decorated = ExtraCheeseDecorator(decorated)
        elif spec.kind == "allergen_flag":
            decorated = AllergenFlagDecorator(decorated, spec.payload.get("allergen", "unknown"))
        elif spec.kind == "substitution":
            decorated = SubstitutionDecorator(
                decorated,
                spec.payload.get("from", "?"),
                spec.payload.get("to", "?"),
                float(spec.payload.get("price_delta", 0.0)),
            )
        else:
            raise ConflictError(f"Unknown decorator kind: {spec.kind}")
    return decorated


# ---------- Factory Method ----------

class MenuItemFactory(ABC):
    location_code: str = "STANDARD"

    @abstractmethod
    def build(self, model: MenuItemModel, children: list[MenuItemModel]) -> MenuItem: ...

    def _to_component(self, model: MenuItemModel, all_children: list[MenuItemModel]) -> MenuItem:
        if model.is_combo:
            child_components = [
                self._to_component(c, all_children) for c in (model.children or [])
            ]
            return ComboMeal(model, child_components)
        return SimpleMenuItem(model)


class StandardMenuFactory(MenuItemFactory):
    location_code = "STANDARD"

    def build(self, model: MenuItemModel, children: list[MenuItemModel]) -> MenuItem:
        return self._to_component(model, children)


class CoastalMenuFactory(MenuItemFactory):
    location_code = "COASTAL"

    def build(self, model: MenuItemModel, children: list[MenuItemModel]) -> MenuItem:
        component = self._to_component(model, children)
        if "fish" in (model.allergens or []):
            return AllergenFlagDecorator(component, "fish")
        return component


class CityCentreMenuFactory(MenuItemFactory):
    location_code = "CITY_CENTRE"

    def build(self, model: MenuItemModel, children: list[MenuItemModel]) -> MenuItem:
        return self._to_component(model, children)


_FACTORIES: dict[str, MenuItemFactory] = {
    f.location_code: f
    for f in [StandardMenuFactory(), CoastalMenuFactory(), CityCentreMenuFactory()]
}


def get_factory(location_code: str | None = None) -> MenuItemFactory:
    code = location_code or settings.LOCATION_CODE
    return _FACTORIES.get(code, _FACTORIES["STANDARD"])


# ---------- Service entry points ----------

class MenuService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = MenuRepository(session)

    async def get_item(self, item_id: uuid.UUID) -> MenuItemDTO:
        model = await self.repo.get(item_id)
        if model is None:
            raise NotFoundError(f"Menu item {item_id} not found")
        return MenuItemDTO.model_validate(model)

    async def update_item(self, item_id: uuid.UUID, dto: dict) -> MenuItemDTO:
        model = await self.repo.get(item_id)
        if model is None:
            raise NotFoundError(f"Menu item {item_id} not found")
        for key, value in dto.items():
            if value is not None:
                setattr(model, key, value)
        await self.session.flush()
        return MenuItemDTO.model_validate(model)

    async def delete_item(self, item_id: uuid.UUID) -> None:
        model = await self.repo.get(item_id)
        if model is None:
            raise NotFoundError(f"Menu item {item_id} not found")
        await self.repo.delete(model)

    async def create_item(self, dto: MenuItemCreateDTO) -> MenuItemDTO:
        model = MenuItemModel(
            name=dto.name,
            description=dto.description,
            base_price=dto.base_price,
            category=dto.category,
            is_combo=dto.is_combo,
            parent_id=dto.parent_id,
            location_code=settings.LOCATION_CODE,
            allergens=dto.allergens,
        )
        await self.repo.add(model)
        return MenuItemDTO.model_validate(model)

    async def list_for_location(self) -> list[MenuItemDTO]:
        models = await self.repo.list_for_location(settings.LOCATION_CODE)
        return [MenuItemDTO.model_validate(m) for m in models]

    async def price_with_decorators(
        self, item_id: uuid.UUID, decorators: list[DecoratorSpecDTO]
    ) -> PricedMenuItemDTO:
        model = await self.repo.get(item_id)
        if model is None:
            raise NotFoundError(f"Menu item {item_id} not found")
        factory = get_factory()
        component = factory.build(model, model.children or [])
        decorated = apply_decorators(component, decorators)
        return PricedMenuItemDTO(
            item_id=model.id,
            name=decorated.name,
            base_price=float(model.base_price),
            decorated_price=decorated.get_price(),
            decorators_applied=[d.kind for d in decorators],
            allergens=decorated.get_allergens(),
            children=[],
        )

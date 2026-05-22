import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.core.exceptions import InvalidStateTransition
from app.dto.menu import DecoratorSpecDTO
from app.models.menu_item import MenuItemModel
from app.services.kitchen import (
    CancelOrderCommand,
    ExpediteOrderCommand,
    KitchenQueue,
    PrepareOrderCommand,
)
from app.services.menu import (
    ComboMeal,
    SimpleMenuItem,
    apply_decorators,
    get_factory,
)
from app.services.pricing import (
    GroupDiscountPricing,
    PricingContext,
    PricingStrategySelector,
    StandardPricing,
)
from app.services.tables import (
    FreeState,
    OccupiedState,
    ReservedState,
    TableContext,
)


def make_menu_model(name="Burger", price=10.0, is_combo=False, allergens=None):
    return MenuItemModel(
        id=uuid.uuid4(),
        name=name,
        description=None,
        base_price=price,
        category="main",
        is_combo=is_combo,
        parent_id=None,
        location_code="STANDARD",
        available=True,
        allergens=allergens or [],
    )


def test_composite_combines_children_prices():
    burger = SimpleMenuItem(make_menu_model("Burger", 10.0))
    fries = SimpleMenuItem(make_menu_model("Fries", 4.0))
    drink = SimpleMenuItem(make_menu_model("Drink", 2.5))
    combo = ComboMeal(make_menu_model("Combo", 0.0, is_combo=True), [burger, fries, drink])
    assert combo.get_price() == 16.5
    assert {t["name"] for t in combo.to_kitchen_tickets()} == {"Burger", "Fries", "Drink"}


def test_decorator_adds_price_and_kitchen_mods():
    burger = SimpleMenuItem(make_menu_model("Burger", 10.0))
    decorated = apply_decorators(
        burger,
        [
            DecoratorSpecDTO(kind="extra_cheese"),
            DecoratorSpecDTO(
                kind="substitution",
                payload={"from": "bun", "to": "lettuce wrap", "price_delta": 1.0},
            ),
        ],
    )
    assert decorated.get_price() == 11.5
    tickets = decorated.to_kitchen_tickets()
    assert any("extra cheese" in m for m in tickets[0].get("mods", []))
    assert any("lettuce wrap" in m for m in tickets[0].get("mods", []))


def test_factory_returns_for_known_location():
    standard = get_factory("STANDARD")
    coastal = get_factory("COASTAL")
    assert standard.__class__.__name__ == "StandardMenuFactory"
    assert coastal.__class__.__name__ == "CoastalMenuFactory"


def test_state_pattern_legal_transitions():
    model = SimpleNamespace(status=FreeState.name, current_order_id=None)
    ctx = TableContext(model)  # pyright: ignore[reportArgumentType]
    ctx.apply("reserve")
    assert isinstance(ctx.state, ReservedState)
    ctx.apply("seat")
    assert isinstance(ctx.state, OccupiedState)
    ctx.apply("attach_order", order_id="order-1")
    assert model.current_order_id == "order-1"


def test_state_pattern_illegal_transition_raises():
    model = SimpleNamespace(status=FreeState.name, current_order_id=None)
    ctx = TableContext(model)  # pyright: ignore[reportArgumentType]
    with pytest.raises(InvalidStateTransition):
        ctx.apply("request_bill")


def test_command_undo_restores_kitchen_state():
    queue = KitchenQueue()
    order_id = uuid.uuid4()
    queue.submit(PrepareOrderCommand(order_id=order_id))
    assert len(queue._pending) == 1
    queue.submit(ExpediteOrderCommand(order_id=order_id))
    queue.undo_last()
    queue.undo_last()
    assert len(queue._pending) == 0


def test_command_cancel_tracks_waste():
    queue = KitchenQueue()
    order_id = uuid.uuid4()
    queue.submit(PrepareOrderCommand(order_id=order_id))
    queue.start_next()
    queue.submit(CancelOrderCommand(order_id=order_id))
    assert queue.waste_count == 1


def test_strategy_selector_picks_group_for_large_party():
    selector = PricingStrategySelector()
    strategy = selector.select(PricingContext(party_size=8))
    assert isinstance(strategy, GroupDiscountPricing)


def test_strategy_standard_when_no_other_signals():
    selector = PricingStrategySelector()
    weekday_midday = datetime(2026, 5, 19, 12, 0)
    strategy = selector.select(PricingContext(now=weekday_midday))
    assert isinstance(strategy, StandardPricing)


def test_singleton_repository_is_shared():
    from app.services.history import _OrderHistoryRepository

    a = _OrderHistoryRepository()
    b = _OrderHistoryRepository()
    assert a is b


def test_iterators_filter_correctly():
    from app.services.history import (
        DateRangeIterator,
        HistoryEntry,
        TopItemsIterator,
        _OrderHistoryRepository,
    )

    repo = _OrderHistoryRepository()
    repo._entries.clear()  # isolate from other tests  # pyright: ignore[reportAttributeAccessIssue]
    base = datetime(2026, 5, 20, 12, 0)
    repo.append(
        HistoryEntry(
            order_id="o1",
            table_id="t1",
            placed_at=base,
            total=10.0,
            items=[{"name": "Burger", "quantity": 2, "unit_price": 5.0}],
        )
    )
    repo.append(
        HistoryEntry(
            order_id="o2",
            table_id="t1",
            placed_at=base,
            total=4.0,
            items=[{"name": "Fries", "quantity": 1, "unit_price": 4.0}],
        )
    )

    entries = list(DateRangeIterator(repo, datetime(2026, 5, 20), datetime(2026, 5, 21)))
    assert len(entries) == 2

    top = list(TopItemsIterator(repo, limit=2))
    assert top[0]["name"] == "Burger"
    assert top[0]["times_ordered"] == 2

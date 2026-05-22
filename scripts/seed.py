"""Seed the BitePlate DB with ~10,000 fake records.

Distribution:
- ~200 menu items (including ~30 category nodes for Composite pattern)
-  ~50 tables
- ~500 reservations
- ~2,000 orders
- ~5,000 order_items (2-3 per order)
- ~2,000 bills (one per closed order)
≈ ~9,750 total rows

Usage (inside a pod):
    kubectl -n biteplate exec deploy/biteplate-api -- python -m scripts.seed
    # with --clear to wipe existing rows first
    kubectl -n biteplate exec deploy/biteplate-api -- python -m scripts.seed --clear

Locally (with a running DATABASE_URL in env):
    python -m scripts.seed --clear
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from faker import Faker
from sqlalchemy import delete, select

from app.database import SessionLocal, dispose_engine
from app.models.bill import Bill
from app.models.menu_item import MenuItemModel
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.reservation import Reservation
from app.models.table import TableModel

fake = Faker()
Faker.seed(42)
random.seed(42)

# ----- Tunable sizes -----
N_CATEGORIES = 30
N_MENU_ITEMS = 170          # 30 categories + 170 items ≈ 200
N_TABLES = 50
N_RESERVATIONS = 500
N_ORDERS = 2_000
ITEMS_PER_ORDER_RANGE = (2, 4)   # avg ~2.5 → ~5,000 order_items
BILL_RATE = 1.0                  # 100% of orders get a bill

CATEGORY_NAMES = [
    "Appetizers", "Salads", "Soups", "Pizzas", "Pastas", "Burgers", "Steaks",
    "Seafood", "Sushi", "Sandwiches", "Wraps", "Tacos", "Curry", "Rice Bowls",
    "Noodles", "Vegan", "Vegetarian", "Kids Menu", "Sides", "Desserts",
    "Ice Cream", "Cakes", "Pastries", "Hot Drinks", "Cold Drinks",
    "Smoothies", "Cocktails", "Wines", "Beers", "Mocktails",
]

ITEM_NAMES = [
    "Margherita Pizza", "Pepperoni Pizza", "BBQ Chicken Pizza", "Caesar Salad",
    "Greek Salad", "Cobb Salad", "Tomato Soup", "Mushroom Soup", "Pho Bowl",
    "Ramen", "Pad Thai", "Beef Stroganoff", "Spaghetti Carbonara", "Lasagna",
    "Cheeseburger", "Bacon Burger", "Veggie Burger", "Ribeye Steak", "T-Bone Steak",
    "Grilled Salmon", "Fish & Chips", "California Roll", "Spicy Tuna Roll",
    "Club Sandwich", "BLT Sandwich", "Chicken Wrap", "Beef Taco", "Chicken Curry",
    "Lamb Biryani", "Vegetable Stir Fry", "Tofu Bowl", "Falafel Plate",
    "Buddha Bowl", "Chicken Nuggets", "French Fries", "Onion Rings",
    "Sweet Potato Fries", "Garlic Bread", "Mozzarella Sticks", "Chocolate Cake",
    "Cheesecake", "Tiramisu", "Apple Pie", "Vanilla Ice Cream", "Chocolate Ice Cream",
    "Strawberry Smoothie", "Mango Smoothie", "Espresso", "Cappuccino", "Latte",
    "Iced Coffee", "Iced Tea", "Lemonade", "Mojito", "Margarita", "Old Fashioned",
    "Red Wine", "White Wine", "IPA Beer", "Lager Beer", "Virgin Mojito",
]

PRICING_STRATEGIES = ["standard", "happy_hour", "member", "surge", "festive"]
ORDER_STATUSES = ["placed", "preparing", "ready", "served", "closed", "cancelled"]
TABLE_STATUSES = ["free", "occupied", "reserved", "cleaning"]
BILL_STATUSES = ["unpaid", "paid", "refunded"]
PAYMENT_METHODS = ["cash", "card", "mobile"]
ALLERGENS_POOL = ["gluten", "dairy", "nuts", "soy", "shellfish", "eggs", "fish"]


async def clear_all(session) -> None:
    """Truncate in FK-safe order."""
    print("Clearing existing rows...")
    for model in (Bill, OrderItem, Order, Reservation, MenuItemModel, TableModel):
        await session.execute(delete(model))
    await session.commit()
    print("Cleared.")


async def seed_menu(session) -> tuple[list[uuid.UUID], list[MenuItemModel]]:
    """Create categories (composite parents) + items. Return (category_ids, all_items)."""
    print(f"Seeding {N_CATEGORIES} categories + {N_MENU_ITEMS} menu items...")
    categories: list[MenuItemModel] = []
    for name in CATEGORY_NAMES[:N_CATEGORIES]:
        cat = MenuItemModel(
            name=name,
            description=f"All our {name.lower()} in one place",
            base_price=Decimal("0.00"),
            category=name.lower().replace(" ", "_"),
            is_combo=True,
            available=True,
            location_code="STANDARD",
            allergens=[],
        )
        session.add(cat)
        categories.append(cat)
    await session.flush()  # get IDs

    items: list[MenuItemModel] = []
    for i in range(N_MENU_ITEMS):
        parent = random.choice(categories)
        base_name = random.choice(ITEM_NAMES)
        suffix = random.choice(["", " Special", " Deluxe", " Classic", " Royal", ""])
        item = MenuItemModel(
            name=f"{base_name}{suffix}".strip() + f" #{i}",
            description=fake.sentence(nb_words=10),
            base_price=Decimal(str(round(random.uniform(3.5, 45.0), 2))),
            category=parent.category,
            is_combo=False,
            parent_id=parent.id,
            available=random.random() > 0.05,  # 5% unavailable
            location_code=random.choice(["STANDARD", "VIP", "TERRACE"]),
            allergens=random.sample(ALLERGENS_POOL, k=random.randint(0, 3)),
        )
        session.add(item)
        items.append(item)
    await session.flush()
    print(f"  → {len(categories)} categories, {len(items)} items inserted")
    return [c.id for c in categories], items


async def seed_tables(session) -> list[TableModel]:
    print(f"Seeding {N_TABLES} tables...")
    tables = []
    for n in range(1, N_TABLES + 1):
        t = TableModel(
            number=n,
            seats=random.choice([2, 2, 4, 4, 4, 6, 6, 8, 10]),
            status=random.choices(
                TABLE_STATUSES, weights=[60, 20, 15, 5], k=1
            )[0],
        )
        session.add(t)
        tables.append(t)
    await session.flush()
    print(f"  → {len(tables)} tables inserted")
    return tables


async def seed_reservations(session, tables: list[TableModel]) -> int:
    print(f"Seeding {N_RESERVATIONS} reservations...")
    now = datetime.now(timezone.utc)
    for _ in range(N_RESERVATIONS):
        table = random.choice(tables)
        booking_time = now + timedelta(
            days=random.randint(-30, 30),
            hours=random.randint(0, 23),
            minutes=random.choice([0, 15, 30, 45]),
        )
        r = Reservation(
            table_id=table.id,
            customer_sub=str(uuid.uuid4()),
            customer_phone=fake.phone_number()[:32],
            customer_name=fake.name(),
            party_size=random.randint(1, min(table.seats, 10)),
            booking_time=booking_time,
            status=random.choices(
                ["confirmed", "seated", "cancelled", "no_show"],
                weights=[60, 25, 10, 5],
            )[0],
        )
        session.add(r)
    await session.flush()
    print(f"  → {N_RESERVATIONS} reservations inserted")
    return N_RESERVATIONS


async def seed_orders_items_bills(
    session,
    tables: list[TableModel],
    menu_items: list[MenuItemModel],
) -> tuple[int, int, int]:
    """Bulk-insert orders, their items, and bills for closed orders."""
    available_items = [m for m in menu_items if m.available]
    waiter_subs = [str(uuid.uuid4()) for _ in range(8)]      # ~8 waiters
    cashier_subs = [str(uuid.uuid4()) for _ in range(4)]     # ~4 cashiers

    print(f"Seeding {N_ORDERS} orders (+ items + bills)...")
    total_items = 0
    total_bills = 0

    # Batch in chunks to keep memory bounded
    CHUNK = 200
    for chunk_start in range(0, N_ORDERS, CHUNK):
        for _ in range(min(CHUNK, N_ORDERS - chunk_start)):
            table = random.choice(tables)
            status = random.choices(
                ORDER_STATUSES, weights=[10, 15, 15, 20, 35, 5]
            )[0]
            strategy = random.choices(
                PRICING_STRATEGIES, weights=[60, 15, 10, 5, 10]
            )[0]

            order = Order(
                table_id=table.id,
                waiter_sub=random.choice(waiter_subs),
                status=status,
                pricing_strategy=strategy,
                notes=fake.sentence(nb_words=6) if random.random() < 0.2 else None,
                subtotal=Decimal("0"),
                total=Decimal("0"),
            )
            session.add(order)
            await session.flush()  # need order.id for OrderItems

            # 2-4 items per order
            n_items = random.randint(*ITEMS_PER_ORDER_RANGE)
            subtotal = Decimal("0")
            for _ in range(n_items):
                mi = random.choice(available_items)
                qty = random.randint(1, 3)
                unit_price = Decimal(str(mi.base_price))
                subtotal += unit_price * qty
                decorators = []
                # randomly attach a decorator (Decorator pattern)
                if random.random() < 0.15:
                    decorators.append({"kind": "discount", "pct": 10})
                if random.random() < 0.10:
                    decorators.append({"kind": "tax", "pct": 8})
                oi = OrderItem(
                    order_id=order.id,
                    menu_item_id=mi.id,
                    menu_item_name=mi.name,
                    quantity=qty,
                    unit_price=unit_price,
                    decorators=decorators,
                    status=random.choice(["pending", "preparing", "ready", "served"]),
                )
                session.add(oi)
                total_items += 1

            # Apply pricing strategy adjustment (simplified)
            strategy_multiplier = {
                "standard": Decimal("1.00"),
                "happy_hour": Decimal("0.85"),
                "member": Decimal("0.90"),
                "surge": Decimal("1.20"),
                "festive": Decimal("1.10"),
            }[strategy]
            order.subtotal = subtotal
            order.total = (subtotal * strategy_multiplier).quantize(Decimal("0.01"))

            # closed orders → bills
            if status in ("served", "closed") and random.random() < BILL_RATE:
                tax = (order.total * Decimal("0.08")).quantize(Decimal("0.01"))
                bill_total = (order.total + tax).quantize(Decimal("0.01"))
                bill = Bill(
                    order_id=order.id,
                    subtotal=order.subtotal,
                    tax=tax,
                    total=bill_total,
                    splits=[],
                    pricing_strategy=strategy,
                    status=random.choices(
                        BILL_STATUSES, weights=[20, 75, 5]
                    )[0],
                    cashier_sub=random.choice(cashier_subs),
                    payment_method=random.choice(PAYMENT_METHODS),
                )
                session.add(bill)
                total_bills += 1

        await session.commit()
        sys.stdout.write(f"  ...{chunk_start + CHUNK}/{N_ORDERS} orders\r")
        sys.stdout.flush()

    print()
    print(f"  → {N_ORDERS} orders, {total_items} order_items, {total_bills} bills inserted")
    return N_ORDERS, total_items, total_bills


async def main(clear: bool) -> None:
    async with SessionLocal() as session:
        if clear:
            await clear_all(session)

        _, menu_items = await seed_menu(session)
        await session.commit()

        tables = await seed_tables(session)
        await session.commit()

        n_res = await seed_reservations(session, tables)
        await session.commit()

        n_ord, n_items, n_bills = await seed_orders_items_bills(session, tables, menu_items)

        # final tally
        async def count(model):
            return (await session.execute(select(model))).scalars().all().__len__()

        print()
        print("=" * 50)
        print("Final row counts:")
        print(f"  menu_items   : {await count(MenuItemModel):>6}")
        print(f"  tables       : {await count(TableModel):>6}")
        print(f"  reservations : {await count(Reservation):>6}")
        print(f"  orders       : {await count(Order):>6}")
        print(f"  order_items  : {await count(OrderItem):>6}")
        print(f"  bills        : {await count(Bill):>6}")
        print("=" * 50)

    await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Wipe all existing rows in seeded tables before inserting.",
    )
    args = parser.parse_args()
    asyncio.run(main(clear=args.clear))

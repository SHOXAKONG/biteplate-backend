from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.dto.orders import OrderCreateDTO, OrderDTO
from app.models.order import Order
from app.models.order_item import OrderItem
from app.repositories.menu import MenuRepository
from app.repositories.order import OrderRepository
from app.services.kitchen import PrepareOrderCommand, kitchen_queue
from app.services.menu import apply_decorators, get_factory
from app.services.notifications import OrderEvent, order_subject
from app.services.pricing import PricingContext, PricingService
from app.services.tables import TableService


class OrderService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.orders = OrderRepository(session)
        self.menu = MenuRepository(session)
        self.tables = TableService(session)
        self.pricing = PricingService()

    async def place_order(self, dto: OrderCreateDTO, waiter_sub: str) -> OrderDTO:
        factory = get_factory()
        order = Order(table_id=dto.table_id, waiter_sub=waiter_sub, notes=dto.notes)
        items: list[OrderItem] = []
        allergens: set[str] = set()

        for line in dto.items:
            model = await self.menu.get(line.menu_item_id)
            if model is None:
                raise NotFoundError(f"Menu item {line.menu_item_id} not found")
            component = factory.build(model, model.children or [])
            decorated = apply_decorators(component, line.decorators)
            unit_price = decorated.get_price()
            allergens.update(decorated.get_allergens())
            items.append(
                OrderItem(
                    menu_item_id=model.id,
                    menu_item_name=model.name,
                    quantity=line.quantity,
                    unit_price=unit_price,
                    decorators=[d.model_dump() for d in line.decorators],
                )
            )

        order.items = items
        order.subtotal = float(sum(i.unit_price * i.quantity for i in items))

        result = self.pricing.price_order(
            Order(items=items, subtotal=order.subtotal, total=order.subtotal),
            PricingContext(now=datetime.utcnow()),
        )
        order.pricing_strategy = result.strategy
        order.total = result.total

        await self.orders.add(order)
        await self.tables.attach_order(dto.table_id, order.id)

        kitchen_queue.submit(PrepareOrderCommand(order_id=order.id))

        order_subject.notify(
            OrderEvent(
                kind="order_placed",
                order_id=str(order.id),
                table_id=str(order.table_id),
                total=order.total,
                payload={
                    "allergens": sorted(allergens),
                    "items": [
                        {
                            "name": i.menu_item_name,
                            "quantity": i.quantity,
                            "unit_price": float(i.unit_price),
                        }
                        for i in items
                    ],
                },
            )
        )
        return OrderDTO.model_validate(order)

    async def confirm_order(self, order_id: uuid.UUID) -> OrderDTO:
        order = await self.orders.get_with_items(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")
        order.status = "confirmed"
        await self.session.flush()
        order_subject.notify(
            OrderEvent(
                kind="order_confirmed",
                order_id=str(order.id),
                table_id=str(order.table_id),
                total=float(order.total),
                payload={
                    "items": [
                        {
                            "name": i.menu_item_name,
                            "quantity": i.quantity,
                            "unit_price": float(i.unit_price),
                        }
                        for i in order.items
                    ]
                },
            )
        )
        return OrderDTO.model_validate(order)

    async def list_orders(self) -> list[OrderDTO]:
        return [OrderDTO.model_validate(o) for o in await self.orders.list_with_items()]

    async def list_by_waiter(self, waiter_sub: str) -> list[OrderDTO]:
        return [OrderDTO.model_validate(o) for o in await self.orders.list_by_waiter(waiter_sub)]

    async def list_by_table(self, table_id: uuid.UUID) -> list[OrderDTO]:
        return [OrderDTO.model_validate(o) for o in await self.orders.list_by_table(table_id)]

    async def cancel_order(self, order_id: uuid.UUID) -> OrderDTO:
        order = await self.orders.get_with_items(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")
        if order.status in ("paid", "cancelled"):
            return OrderDTO.model_validate(order)
        order.status = "cancelled"
        await self.session.flush()
        order_subject.notify(
            OrderEvent(
                kind="order_cancelled",
                order_id=str(order.id),
                table_id=str(order.table_id),
            )
        )
        return OrderDTO.model_validate(order)

    async def get_order(self, order_id: uuid.UUID) -> OrderDTO:
        order = await self.orders.get_with_items(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")
        return OrderDTO.model_validate(order)

"""Billing domain: Facade pattern."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.dto.billing import BillDTO
from app.models.bill import Bill
from app.repositories.bill import BillRepository
from app.repositories.order import OrderRepository
from app.services.pricing import PricingContext, PricingService


class TaxCalculator:
    VAT_RATE = 0.20

    def vat(self, amount: float) -> float:
        return round(amount * self.VAT_RATE, 2)


class SplitBillCalculator:
    def split(self, total: float, count: int) -> list[dict]:
        if count < 1:
            raise ConflictError("split_count must be >= 1")
        base = round(total / count, 2)
        amounts = [base] * count
        remainder = round(total - base * count, 2)
        amounts[-1] = round(amounts[-1] + remainder, 2)
        return [{"index": i, "amount": a} for i, a in enumerate(amounts)]


class BillingFacade:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.orders = OrderRepository(session)
        self.bills = BillRepository(session)
        self.pricing = PricingService()
        self.tax = TaxCalculator()
        self.split = SplitBillCalculator()

    async def list_bills(self, status: str | None = None) -> list[BillDTO]:
        return [BillDTO.model_validate(b) for b in await self.bills.list_all_sorted(status)]

    async def list_by_cashier(self, cashier_sub: str) -> list[BillDTO]:
        return [BillDTO.model_validate(b) for b in await self.bills.list_by_cashier(cashier_sub)]

    async def update_status(
        self, bill_id: uuid.UUID, status: str, payment_method: str | None = None
    ) -> BillDTO:
        bill = await self.bills.get(bill_id)
        if bill is None:
            raise NotFoundError(f"Bill {bill_id} not found")
        bill.status = status
        if payment_method is not None:
            bill.payment_method = payment_method
        await self.session.flush()
        return BillDTO.model_validate(bill)

    async def generate_bill(
        self,
        order_id: uuid.UUID,
        split_count: int = 1,
        cashier_sub: str | None = None,
        pricing_context: PricingContext | None = None,
    ) -> BillDTO:
        order = await self.orders.get_with_items(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")

        existing = await self.bills.get_by_order_id(order_id)
        if existing is not None:
            raise ConflictError(f"Order {order_id} already has a bill")

        result = self.pricing.price_order(order, pricing_context)
        tax = self.tax.vat(result.total)
        final_total = round(result.total + tax, 2)
        splits = self.split.split(final_total, split_count)

        bill = Bill(
            order_id=order.id,
            subtotal=result.subtotal,
            tax=tax,
            total=final_total,
            splits=splits,
            pricing_strategy=result.strategy,
            status="unpaid",
            cashier_sub=cashier_sub,
        )
        await self.bills.add(bill)
        return BillDTO.model_validate(bill)

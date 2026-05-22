"""Pricing domain: Strategy pattern."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.models.order import Order


@dataclass
class PricingContext:
    now: datetime = field(default_factory=datetime.utcnow)
    loyalty_tier: str | None = None
    party_size: int = 1


@dataclass
class PricingResult:
    strategy: str
    subtotal: float
    discount: float
    total: float
    notes: list[str] = field(default_factory=list)


class PricingStrategy(ABC):
    name: str = "abstract"

    @abstractmethod
    def calculate_total(self, order: Order, context: PricingContext) -> PricingResult: ...

    @staticmethod
    def _subtotal(order: Order) -> float:
        return float(sum(float(i.unit_price) * i.quantity for i in (order.items or [])))


class StandardPricing(PricingStrategy):
    name = "standard"

    def calculate_total(self, order: Order, context: PricingContext) -> PricingResult:
        subtotal = self._subtotal(order)
        return PricingResult(self.name, subtotal, 0.0, subtotal, notes=["full price"])


class HappyHourPricing(PricingStrategy):
    name = "happy_hour"
    DISCOUNT = 0.20

    def calculate_total(self, order: Order, context: PricingContext) -> PricingResult:
        subtotal = self._subtotal(order)
        discount = round(subtotal * self.DISCOUNT, 2)
        return PricingResult(
            self.name, subtotal, discount, subtotal - discount, notes=["20% happy hour"]
        )


class LoyaltyCardPricing(PricingStrategy):
    name = "loyalty"
    DISCOUNT = 0.10

    def calculate_total(self, order: Order, context: PricingContext) -> PricingResult:
        subtotal = self._subtotal(order)
        discount = round(subtotal * self.DISCOUNT, 2)
        return PricingResult(
            self.name,
            subtotal,
            discount,
            subtotal - discount,
            notes=["10% loyalty discount", "free drink voucher"],
        )


class WeekendSurchargePricing(PricingStrategy):
    name = "weekend_surcharge"
    SURCHARGE = 0.05

    def calculate_total(self, order: Order, context: PricingContext) -> PricingResult:
        subtotal = self._subtotal(order)
        surcharge = round(subtotal * self.SURCHARGE, 2)
        return PricingResult(
            self.name, subtotal, -surcharge, subtotal + surcharge, notes=["5% weekend surcharge"]
        )


class GroupDiscountPricing(PricingStrategy):
    name = "group_discount"
    DISCOUNT = 0.15

    def calculate_total(self, order: Order, context: PricingContext) -> PricingResult:
        subtotal = self._subtotal(order)
        discount = round(subtotal * self.DISCOUNT, 2)
        return PricingResult(
            self.name,
            subtotal,
            discount,
            subtotal - discount,
            notes=[f"15% group discount (party of {context.party_size})"],
        )


class PricingStrategySelector:
    HAPPY_HOUR_START = 15
    HAPPY_HOUR_END = 17

    def select(self, context: PricingContext) -> PricingStrategy:
        if context.party_size >= 6:
            return GroupDiscountPricing()
        if context.loyalty_tier in ("gold", "platinum"):
            return LoyaltyCardPricing()
        if context.now.weekday() >= 5:
            return WeekendSurchargePricing()
        if self.HAPPY_HOUR_START <= context.now.hour < self.HAPPY_HOUR_END:
            return HappyHourPricing()
        return StandardPricing()


_STRATEGIES_BY_NAME = {
    s.name: s
    for s in [
        StandardPricing(),
        HappyHourPricing(),
        LoyaltyCardPricing(),
        WeekendSurchargePricing(),
        GroupDiscountPricing(),
    ]
}


def strategy_by_name(name: str) -> PricingStrategy:
    return _STRATEGIES_BY_NAME.get(name, StandardPricing())


class PricingService:
    def __init__(self):
        self.selector = PricingStrategySelector()

    def price_order(self, order: Order, context: PricingContext | None = None) -> PricingResult:
        ctx = context or PricingContext()
        strategy = self.selector.select(ctx)
        return strategy.calculate_total(order, ctx)

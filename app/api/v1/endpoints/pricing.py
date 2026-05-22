from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.dependencies import db_session, require_role
from app.dto.pricing import PricingPreviewDTO, PricingResultDTO
from app.repositories.order import OrderRepository
from app.services.pricing import PricingContext, PricingService

router = APIRouter()


@router.post(
    "/preview",
    response_model=PricingResultDTO,
    dependencies=[Depends(require_role("waiter", "manager", "cashier"))],
)
async def preview(dto: PricingPreviewDTO, session: AsyncSession = Depends(db_session)):
    order = await OrderRepository(session).get_with_items(dto.order_id)
    if order is None:
        raise NotFoundError(f"Order {dto.order_id} not found")
    context = PricingContext(loyalty_tier=dto.loyalty_tier, party_size=dto.party_size)
    result = PricingService().price_order(order, context)
    return PricingResultDTO(
        strategy=result.strategy,
        subtotal=result.subtotal,
        discount=result.discount,
        total=result.total,
        notes=result.notes,
    )

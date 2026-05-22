import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import KeycloakUser
from app.dependencies import db_session, get_current_user, require_role
from app.dto.billing import BillDTO, BillRequestDTO, BillStatusUpdateDTO
from app.services.billing import BillingFacade

router = APIRouter()


@router.get(
    "",
    response_model=list[BillDTO],
    dependencies=[Depends(require_role("cashier", "manager"))],
)
async def list_bills(
    status_filter: str | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await BillingFacade(session).list_bills(status_filter)


@router.get(
    "/mine",
    response_model=list[BillDTO],
    dependencies=[Depends(require_role("cashier"))],
)
async def list_my_bills(
    session: AsyncSession = Depends(db_session),  # noqa: B008
    user: KeycloakUser = Depends(get_current_user),  # noqa: B008
):
    return await BillingFacade(session).list_by_cashier(user.sub)


@router.post(
    "",
    response_model=BillDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("cashier", "manager"))],
)
async def generate_bill(
    dto: BillRequestDTO,
    session: AsyncSession = Depends(db_session),  # noqa: B008
    user: KeycloakUser = Depends(get_current_user),  # noqa: B008
):
    return await BillingFacade(session).generate_bill(
        order_id=dto.order_id, split_count=dto.split_count, cashier_sub=user.sub
    )


@router.patch(
    "/{bill_id}",
    response_model=BillDTO,
    dependencies=[Depends(require_role("cashier", "manager"))],
)
async def update_status(
    bill_id: uuid.UUID,
    dto: BillStatusUpdateDTO,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await BillingFacade(session).update_status(
        bill_id=bill_id, status=dto.status, payment_method=dto.payment_method
    )

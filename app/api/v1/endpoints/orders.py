import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import KeycloakUser
from app.dependencies import db_session, get_current_user, require_role
from app.dto.orders import OrderCreateDTO, OrderDTO
from app.services.orders import OrderService

router = APIRouter()


@router.get(
    "",
    response_model=list[OrderDTO],
    dependencies=[Depends(require_role("waiter", "manager", "head_chef", "cashier"))],
)
async def list_orders(
    table_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    svc = OrderService(session)
    if table_id is not None:
        return await svc.list_by_table(table_id)
    return await svc.list_orders()


@router.get(
    "/mine",
    response_model=list[OrderDTO],
    dependencies=[Depends(require_role("waiter", "manager"))],
)
async def list_my_orders(
    session: AsyncSession = Depends(db_session),  # noqa: B008
    user: KeycloakUser = Depends(get_current_user),  # noqa: B008
):
    return await OrderService(session).list_by_waiter(user.sub)


@router.post(
    "",
    response_model=OrderDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("waiter", "manager"))],
)
async def place_order(
    dto: OrderCreateDTO,
    session: AsyncSession = Depends(db_session),  # noqa: B008
    user: KeycloakUser = Depends(get_current_user),  # noqa: B008
):
    return await OrderService(session).place_order(dto, waiter_sub=user.sub)


@router.get("/{order_id}", response_model=OrderDTO)
async def get_order(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await OrderService(session).get_order(order_id)


@router.post(
    "/{order_id}/confirm",
    response_model=OrderDTO,
    dependencies=[Depends(require_role("waiter", "manager"))],
)
async def confirm_order(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await OrderService(session).confirm_order(order_id)


@router.delete(
    "/{order_id}",
    response_model=OrderDTO,
    dependencies=[Depends(require_role("waiter", "manager"))],
)
async def cancel_order(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await OrderService(session).cancel_order(order_id)

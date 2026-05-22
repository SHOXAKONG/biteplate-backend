import uuid

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import db_session, require_role
from app.dto.menu import (
    DecoratorSpecDTO,
    MenuItemCreateDTO,
    MenuItemDTO,
    MenuItemUpdateDTO,
    PricedMenuItemDTO,
)
from app.services.menu import MenuService

router = APIRouter()


@router.get("", response_model=list[MenuItemDTO])
async def list_menu(session: AsyncSession = Depends(db_session)):  # noqa: B008
    return await MenuService(session).list_for_location()


@router.get("/{item_id}", response_model=MenuItemDTO)
async def get_menu_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await MenuService(session).get_item(item_id)


@router.post(
    "",
    response_model=MenuItemDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def create_menu_item(
    dto: MenuItemCreateDTO,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await MenuService(session).create_item(dto)


@router.patch(
    "/{item_id}",
    response_model=MenuItemDTO,
    dependencies=[Depends(require_role("admin"))],
)
async def update_menu_item(
    item_id: uuid.UUID,
    dto: MenuItemUpdateDTO,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await MenuService(session).update_item(item_id, dto.model_dump(exclude_unset=True))


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_menu_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    await MenuService(session).delete_item(item_id)


@router.post(
    "/{item_id}/price",
    response_model=PricedMenuItemDTO,
    dependencies=[Depends(require_role("waiter", "manager", "customer"))],
)
async def price_item(
    item_id: uuid.UUID,
    decorators: list[DecoratorSpecDTO] = Body(default_factory=list),  # noqa: B008
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await MenuService(session).price_with_decorators(item_id, decorators)

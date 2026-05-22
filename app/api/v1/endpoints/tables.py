import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import db_session, require_role
from app.dto.tables import TableActionDTO, TableCreateDTO, TableDTO, TableUpdateDTO
from app.services.tables import TableService

router = APIRouter()


@router.get("", response_model=list[TableDTO])
async def list_tables(session: AsyncSession = Depends(db_session)):  # noqa: B008
    return await TableService(session).list_all()


@router.post(
    "",
    response_model=TableDTO,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def create_table(
    dto: TableCreateDTO,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await TableService(session).create(dto)


@router.patch(
    "/{table_id}",
    response_model=TableDTO,
    dependencies=[Depends(require_role("admin"))],
)
async def update_table(
    table_id: uuid.UUID,
    dto: TableUpdateDTO,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await TableService(session).update(table_id, dto.number, dto.seats)


@router.delete(
    "/{table_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_table(
    table_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    await TableService(session).delete(table_id)


@router.post(
    "/{table_id}/actions",
    response_model=TableDTO,
    dependencies=[Depends(require_role("waiter", "manager"))],
)
async def perform_action(
    table_id: uuid.UUID,
    action: TableActionDTO,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await TableService(session).perform_action(table_id, action.action)

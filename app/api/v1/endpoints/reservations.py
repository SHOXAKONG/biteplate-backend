import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import KeycloakUser
from app.dependencies import db_session, get_current_user
from app.dto.reservations import ReservationCreateDTO, ReservationDTO, ReservationUpdateDTO
from app.services.reservations import ReservationService

router = APIRouter()

STAFF_ROLES = {"admin", "manager", "waiter"}


def _is_staff(user: KeycloakUser) -> bool:
    return any(r in STAFF_ROLES for r in user.roles)


@router.get("", response_model=list[ReservationDTO])
async def list_reservations(
    session: AsyncSession = Depends(db_session),  # noqa: B008
    user: KeycloakUser = Depends(get_current_user),  # noqa: B008
):
    svc = ReservationService(session)
    if _is_staff(user):
        return await svc.list_all()
    return await svc.list_for_customer(user.sub)


@router.get("/mine", response_model=list[ReservationDTO])
async def list_mine(
    session: AsyncSession = Depends(db_session),  # noqa: B008
    user: KeycloakUser = Depends(get_current_user),  # noqa: B008
):
    return await ReservationService(session).list_for_customer(user.sub)


@router.post("", response_model=ReservationDTO, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    dto: ReservationCreateDTO,
    session: AsyncSession = Depends(db_session),  # noqa: B008
    user: KeycloakUser = Depends(get_current_user),  # noqa: B008
):
    return await ReservationService(session).create(dto, customer_sub=user.sub)


@router.get("/{reservation_id}", response_model=ReservationDTO)
async def get_reservation(
    reservation_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),  # noqa: B008
):
    return await ReservationService(session).get(reservation_id)


@router.patch("/{reservation_id}", response_model=ReservationDTO)
async def update_reservation(
    reservation_id: uuid.UUID,
    dto: ReservationUpdateDTO,
    session: AsyncSession = Depends(db_session),  # noqa: B008
    user: KeycloakUser = Depends(get_current_user),  # noqa: B008
):
    return await ReservationService(session).update(
        reservation_id, dto, actor_sub=user.sub, is_staff=_is_staff(user)
    )


@router.delete("/{reservation_id}", response_model=ReservationDTO)
async def cancel_reservation(
    reservation_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),  # noqa: B008
    user: KeycloakUser = Depends(get_current_user),  # noqa: B008
):
    return await ReservationService(session).cancel(
        reservation_id, actor_sub=user.sub, is_staff=_is_staff(user)
    )

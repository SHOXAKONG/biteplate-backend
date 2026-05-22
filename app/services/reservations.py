from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.dto.reservations import ReservationCreateDTO, ReservationDTO, ReservationUpdateDTO
from app.models.reservation import Reservation
from app.repositories.reservation import ReservationRepository
from app.services.notifications import OrderEvent, order_subject


class ReservationService:
    REMINDER_OFFSET = timedelta(hours=2)

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ReservationRepository(session)

    async def create(self, dto: ReservationCreateDTO, customer_sub: str) -> ReservationDTO:
        reservation = Reservation(
            table_id=dto.table_id,
            customer_sub=customer_sub,
            customer_name=dto.customer_name,
            customer_phone=dto.customer_phone,
            party_size=dto.party_size,
            booking_time=dto.booking_time,
            status="confirmed",
        )
        await self.repo.add(reservation)

        task_id = self._schedule_reminder(reservation)
        if task_id:
            reservation.reminder_task_id = task_id
            await self.session.flush()

        order_subject.notify(
            OrderEvent(
                kind="reservation_confirmed",
                order_id=str(reservation.id),
                customer_phone=reservation.customer_phone,
                customer_name=reservation.customer_name,
                payload={"booking_time": reservation.booking_time.isoformat()},
            )
        )
        return ReservationDTO.model_validate(reservation)

    def _schedule_reminder(self, reservation: Reservation) -> str | None:
        try:
            from app.tasks.scheduled import send_reservation_reminder

            eta = reservation.booking_time - self.REMINDER_OFFSET
            result = send_reservation_reminder.apply_async(
                args=[str(reservation.id)], eta=eta
            )
            return result.id
        except Exception:
            return None

    async def get(self, reservation_id: uuid.UUID) -> ReservationDTO:
        model = await self.repo.get(reservation_id)
        if model is None:
            raise NotFoundError(f"Reservation {reservation_id} not found")
        return ReservationDTO.model_validate(model)

    async def list_all(self) -> list[ReservationDTO]:
        return [ReservationDTO.model_validate(m) for m in await self.repo.list_upcoming()]

    async def list_for_customer(self, customer_sub: str) -> list[ReservationDTO]:
        return [
            ReservationDTO.model_validate(m)
            for m in await self.repo.list_by_customer(customer_sub)
        ]

    async def update(
        self,
        reservation_id: uuid.UUID,
        dto: ReservationUpdateDTO,
        actor_sub: str,
        is_staff: bool,
    ) -> ReservationDTO:
        model = await self.repo.get(reservation_id)
        if model is None:
            raise NotFoundError(f"Reservation {reservation_id} not found")
        if not is_staff and model.customer_sub != actor_sub:
            raise ConflictError("You can only modify your own reservation")
        if model.status == "cancelled":
            raise ConflictError("Cannot modify a cancelled reservation")
        if dto.party_size is not None:
            model.party_size = dto.party_size
        if dto.customer_phone is not None:
            model.customer_phone = dto.customer_phone
        if dto.booking_time is not None:
            model.booking_time = dto.booking_time
        await self.session.flush()
        return ReservationDTO.model_validate(model)

    async def cancel(
        self, reservation_id: uuid.UUID, actor_sub: str, is_staff: bool
    ) -> ReservationDTO:
        model = await self.repo.get(reservation_id)
        if model is None:
            raise NotFoundError(f"Reservation {reservation_id} not found")
        if not is_staff and model.customer_sub != actor_sub:
            raise ConflictError("You can only cancel your own reservation")
        if model.status == "cancelled":
            return ReservationDTO.model_validate(model)
        model.status = "cancelled"
        await self.session.flush()
        order_subject.notify(
            OrderEvent(
                kind="reservation_cancelled",
                order_id=str(model.id),
                customer_phone=model.customer_phone,
                customer_name=model.customer_name,
            )
        )
        return ReservationDTO.model_validate(model)

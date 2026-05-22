import uuid
from datetime import datetime

from sqlalchemy import and_, desc, select

from app.models.reservation import Reservation
from app.repositories.base import BaseRepository


class ReservationRepository(BaseRepository[Reservation]):
    model = Reservation

    async def list_for_table_in_range(
        self, table_id: uuid.UUID, start: datetime, end: datetime
    ) -> list[Reservation]:
        stmt = select(Reservation).where(
            and_(
                Reservation.table_id == table_id,
                Reservation.booking_time >= start,
                Reservation.booking_time < end,
                Reservation.status != "cancelled",
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_customer(self, customer_sub: str) -> list[Reservation]:
        stmt = (
            select(Reservation)
            .where(Reservation.customer_sub == customer_sub)
            .order_by(desc(Reservation.booking_time))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_upcoming(self) -> list[Reservation]:
        stmt = (
            select(Reservation)
            .where(Reservation.status != "cancelled")
            .order_by(Reservation.booking_time)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

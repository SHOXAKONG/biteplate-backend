import uuid

from sqlalchemy import desc, select

from app.models.bill import Bill
from app.repositories.base import BaseRepository


class BillRepository(BaseRepository[Bill]):
    model = Bill

    async def get_by_order_id(self, order_id: uuid.UUID) -> Bill | None:
        result = await self.session.execute(select(Bill).where(Bill.order_id == order_id))
        return result.scalar_one_or_none()

    async def list_all_sorted(self, status: str | None = None) -> list[Bill]:
        stmt = select(Bill).order_by(desc(Bill.created_at))
        if status:
            stmt = stmt.where(Bill.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_cashier(self, cashier_sub: str) -> list[Bill]:
        stmt = (
            select(Bill).where(Bill.cashier_sub == cashier_sub).order_by(desc(Bill.created_at))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

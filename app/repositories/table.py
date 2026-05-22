from sqlalchemy import select

from app.models.table import TableModel
from app.repositories.base import BaseRepository


class TableRepository(BaseRepository[TableModel]):
    model = TableModel

    async def get_by_number(self, number: int) -> TableModel | None:
        result = await self.session.execute(
            select(TableModel).where(TableModel.number == number)
        )
        return result.scalar_one_or_none()

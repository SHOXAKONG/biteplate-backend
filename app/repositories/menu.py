from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.menu_item import MenuItemModel
from app.repositories.base import BaseRepository


class MenuRepository(BaseRepository[MenuItemModel]):
    model = MenuItemModel

    async def list_for_location(self, location_code: str) -> list[MenuItemModel]:
        stmt = (
            select(MenuItemModel)
            .where(MenuItemModel.location_code == location_code)
            .where(MenuItemModel.parent_id.is_(None))
            .options(selectinload(MenuItemModel.children))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

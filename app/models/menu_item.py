import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base, TimestampMixin, UUIDPKMixin


class MenuItemModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "menu_items"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    base_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="main")
    is_combo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("menu_items.id", ondelete="CASCADE")
    )
    location_code: Mapped[str] = mapped_column(String(50), nullable=False, default="STANDARD")
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allergens: Mapped[dict] = mapped_column(JSONB, default=list, nullable=False)

    children: Mapped[list["MenuItemModel"]] = relationship(
        "MenuItemModel",
        backref="parent",
        remote_side="MenuItemModel.id",
        cascade="all, delete-orphan",
        single_parent=True,
    )

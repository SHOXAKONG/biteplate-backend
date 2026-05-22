from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base, TimestampMixin, UUIDPKMixin


class TableModel(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "tables"

    number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="free")
    current_order_id: Mapped[str | None] = mapped_column(String(64))

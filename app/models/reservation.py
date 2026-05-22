import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base, TimestampMixin, UUIDPKMixin


class Reservation(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "reservations"

    table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tables.id", ondelete="CASCADE"), nullable=False
    )
    customer_sub: Mapped[str] = mapped_column(String(64), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    booking_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="confirmed")
    reminder_task_id: Mapped[str | None] = mapped_column(String(128))

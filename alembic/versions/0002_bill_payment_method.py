"""add payment_method column to bills

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bills", sa.Column("payment_method", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "payment_method")

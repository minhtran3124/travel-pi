"""bookings confirmation_code unique index

Promote ``ix_bookings_confirmation_code`` from a plain index to a UNIQUE one
(partial, ``WHERE confirmation_code IS NOT NULL``) so the derived 6-char
confirmation code is a sound alternate lookup key. Booking-ID minting is
collision-aware (``BookingService._mint_booking_id``), so the unique constraint
never surfaces as an insert failure.

Revision ID: c3e5a7b9d1f2
Revises: 7b300c56abff
Create Date: 2026-06-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e5a7b9d1f2"
down_revision: str | Sequence[str] | None = "7b300c56abff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOT_NULL = sa.text("confirmation_code IS NOT NULL")


def upgrade() -> None:
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.drop_index("ix_bookings_confirmation_code")
        batch_op.create_index(
            "ix_bookings_confirmation_code",
            ["confirmation_code"],
            unique=True,
            sqlite_where=_NOT_NULL,
            postgresql_where=_NOT_NULL,
        )


def downgrade() -> None:
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.drop_index(
            "ix_bookings_confirmation_code",
            sqlite_where=_NOT_NULL,
            postgresql_where=_NOT_NULL,
        )
        batch_op.create_index(
            "ix_bookings_confirmation_code",
            ["confirmation_code"],
            unique=False,
        )

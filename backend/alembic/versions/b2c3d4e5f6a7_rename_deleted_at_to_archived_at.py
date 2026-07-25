"""rename deleted_at to archived_at

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "programs",
        "deleted_at",
        new_column_name="archived_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )
    # Under the old soft-delete mechanic, a soft-deleted program could still have
    # is_active=true (masked by the now-removed archived_at IS NULL filter in
    # get_active_program). The new "archived implies not active" invariant relies on
    # is_active alone, so backfill it here or a migrated archived row could still be
    # returned as the user's active program.
    op.execute("UPDATE programs SET is_active = false WHERE archived_at IS NOT NULL")


def downgrade() -> None:
    op.alter_column(
        "programs",
        "archived_at",
        new_column_name="deleted_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
    )

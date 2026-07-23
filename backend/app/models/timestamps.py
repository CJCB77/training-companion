from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field


# These return a *fresh* Field (with its own sa.Column) on every call. A single
# sa.Column instance cannot be shared across tables — SQLAlchemy raises
# "Column object already assigned to Table" — so a mixin holding the columns
# would break. Functions sidestep that while keeping the definition in one place.
# Mirrors the inline timestamp pattern already used in app/models/profile.py.


def created_at_column() -> datetime | None:
    return Field(
        default=None,
        sa_column=sa.Column(
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def updated_at_column() -> datetime | None:
    return Field(
        default=None,
        sa_column=sa.Column(
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

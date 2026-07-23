from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from app.models.enums import WeightUnit


class Profile(SQLModel, table=True):
    __tablename__ = "profiles"

    id: int | None = Field(default=None, primary_key=True)
    supabase_user_id: UUID = Field(
        sa_column=sa.Column(
            PG_UUID(as_uuid=True), unique=True, index=True, nullable=False
        ),
    )
    email: str
    name: str | None = None
    # Default unit applied to new programs the user creates. Authoritative unit lives
    # on each Program (Program.weight_unit).
    default_weight_unit: WeightUnit = Field(
        sa_column=sa.Column(sa.String, nullable=False, server_default=WeightUnit.KG)
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

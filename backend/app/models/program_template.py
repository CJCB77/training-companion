from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.enums import ProgressionType, WeightUnit
from app.models.timestamps import created_at_column, updated_at_column


class ProgramTemplate(SQLModel, table=True):
    """A reusable, read-only system-seeded program structure (StrongLifts 5x5,
    Starting Strength, Texas Method, ...) used as an onboarding accelerator — see
    CLAUDE.md's `ProgramTemplate` domain entity and TRAIN-24's design plan.

    Deliberately **no** `is_active` / `archived_at` / lifecycle columns: templates
    are read-only system data with no lifecycle of their own, so CLAUDE.md's Entity
    Lifecycle Conventions three-way split does not apply here. Seeded exclusively via
    Alembic migration (mirroring the system `Exercise` seed in `879db719772b`) — there
    is no create/update/delete endpoint, matching the "read-only system data" AC.

    `structure` holds the week/session/prescription tree as JSONB, validated against
    `app.schemas.program_templates.TemplateStructure` at read/generate time rather than
    mirrored across relational tables (see TRAIN-24's "Storage" resolved question).
    No ORM `Relationship` toward `Program`: generation only ever *reads* this row to
    build an independent copy, and there is no provenance FK linking generated
    programs back to their template (see TRAIN-24's "no provenance FK" decision).
    """

    __tablename__ = "program_templates"

    id: int | None = Field(default=None, primary_key=True)
    # Stable identifier used by the seed migration for idempotency/downgrade, and
    # exposed in the read schema.
    slug: str = Field(
        sa_column=sa.Column(sa.String, unique=True, index=True, nullable=False)
    )
    name: str
    description: str | None = None

    weight_unit: WeightUnit = Field(
        sa_column=sa.Column(sa.String, nullable=False, server_default=WeightUnit.KG)
    )
    default_progression_type: ProgressionType | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    default_progression_params: dict | None = Field(
        default=None, sa_column=sa.Column(JSONB, nullable=True)
    )

    # The week -> session -> prescription tree. Not null: a template with no
    # structure isn't generatable, so there is nothing valid an empty row would mean.
    structure: dict = Field(sa_column=sa.Column(JSONB, nullable=False))

    created_at: datetime | None = created_at_column()
    updated_at: datetime | None = updated_at_column()

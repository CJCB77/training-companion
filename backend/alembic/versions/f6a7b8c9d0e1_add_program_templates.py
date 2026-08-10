"""add program templates

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.data.seed_program_templates import PROGRAM_TEMPLATE_SEED

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Ad-hoc table reference so this migration is independent of the live model,
# matching 879db719772b's precedent for the system Exercise seed.
_program_templates = sa.table(
    "program_templates",
    sa.column("slug", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("weight_unit", sa.String),
    sa.column("default_progression_type", sa.String),
    sa.column("default_progression_params", JSONB),
    sa.column("structure", JSONB),
)


def upgrade() -> None:
    op.create_table(
        "program_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "weight_unit", sa.String(), server_default="kg", nullable=False
        ),
        sa.Column("default_progression_type", sa.String(), nullable=True),
        sa.Column("default_progression_params", JSONB(), nullable=True),
        sa.Column("structure", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_program_templates_slug"),
        "program_templates",
        ["slug"],
        unique=True,
    )

    op.bulk_insert(
        _program_templates,
        [
            {
                "slug": row["slug"],
                "name": row["name"],
                "description": row.get("description"),
                "weight_unit": str(row["weight_unit"]),
                "default_progression_type": (
                    str(row["default_progression_type"])
                    if row.get("default_progression_type")
                    else None
                ),
                "default_progression_params": row.get("default_progression_params"),
                "structure": row["structure"],
            }
            for row in PROGRAM_TEMPLATE_SEED
        ],
    )


def downgrade() -> None:
    # Dropping the table implicitly removes the seed rows too, so there is no
    # separate delete-by-slug step (unlike 879db719772b, which only added rows to
    # an already-existing table).
    op.drop_index(op.f("ix_program_templates_slug"), table_name="program_templates")
    op.drop_table("program_templates")

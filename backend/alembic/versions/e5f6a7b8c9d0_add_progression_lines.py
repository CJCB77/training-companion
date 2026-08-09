"""add progression lines

Revision ID: e5f6a7b8c9d0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-09 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "progression_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("label", sa.String(), nullable=True),
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
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_progression_lines_program_id"),
        "progression_lines",
        ["program_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_progression_lines_exercise_id"),
        "progression_lines",
        ["exercise_id"],
        unique=False,
    )
    # At most one default line per (program, exercise). Explicit split lines stay
    # unconstrained.
    op.create_index(
        "ix_progression_lines_default_per_program_exercise",
        "progression_lines",
        ["program_id", "exercise_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    # No backfill: the database has no existing exercise_prescriptions rows to
    # reconcile (pre-MVP, nothing live yet), so the column is added NOT NULL
    # directly rather than nullable-then-backfill-then-locked-down.
    op.add_column(
        "exercise_prescriptions",
        sa.Column("progression_line_id", sa.Integer(), nullable=False),
    )
    op.create_foreign_key(
        "fk_exercise_prescriptions_progression_line_id",
        "exercise_prescriptions",
        "progression_lines",
        ["progression_line_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_exercise_prescriptions_progression_line_id"),
        "exercise_prescriptions",
        ["progression_line_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_exercise_prescriptions_progression_line_id"),
        table_name="exercise_prescriptions",
    )
    op.drop_constraint(
        "fk_exercise_prescriptions_progression_line_id",
        "exercise_prescriptions",
        type_="foreignkey",
    )
    op.drop_column("exercise_prescriptions", "progression_line_id")

    op.drop_index(
        "ix_progression_lines_default_per_program_exercise",
        table_name="progression_lines",
    )
    op.drop_index(
        op.f("ix_progression_lines_exercise_id"), table_name="progression_lines"
    )
    op.drop_index(
        op.f("ix_progression_lines_program_id"), table_name="progression_lines"
    )
    op.drop_table("progression_lines")

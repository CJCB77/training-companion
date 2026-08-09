from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.models.timestamps import created_at_column, updated_at_column


class ProgressionLine(SQLModel, table=True):
    """Groups `ExercisePrescription`s of the same exercise, within the same program,
    into one shared progression history — see CLAUDE.md's "Progression Lines".

    Eagerly materialized: a row exists for every `(program, exercise)` pair from the
    first prescription that uses it, `is_default=True`. There is no NULL-means-default
    convention anywhere — `ExercisePrescription.progression_line_id` is NOT NULL.

    Deliberately no ORM `Relationship` to/from `Program` or `ExercisePrescription` in
    either direction. The scoping query (`list_prior_attempts`) reads the column
    directly, and keeping this model out of the ORM's unit-of-work delete graph is what
    lets `programs_repo.delete_program` keep working unchanged: `session.delete(program)`
    cascades weeks -> sessions -> prescriptions through the already-declared
    relationships and deletes the program row; only then does the DB-level cascade
    remove `progression_lines`, by which point nothing references them, so the
    `exercise_id` RESTRICT never fires. Adding relationships here would put lines and
    prescriptions in the same unit-of-work delete graph and reintroduce an ordering
    hazard for no benefit.
    """

    __tablename__ = "progression_lines"
    __table_args__ = (
        # At most one default line per (program, exercise). Explicit split lines
        # stay unconstrained — a program may have any number of extra lines for the
        # same exercise, labeled or not.
        sa.Index(
            "ix_progression_lines_default_per_program_exercise",
            "program_id",
            "exercise_id",
            unique=True,
            postgresql_where=sa.text("is_default"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    program_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("programs.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    # RESTRICT: same rule ExercisePrescription.exercise_id already uses — an exercise
    # referenced by a line cannot be deleted out from under it.
    exercise_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("exercises.id", ondelete="RESTRICT"),
            index=True,
            nullable=False,
        )
    )
    # A real column rather than inferring "the default is the one with no label" or
    # "the oldest one": the label must stay decorative per CLAUDE.md, and an inferred
    # default has no DB-enforceable invariant behind it.
    is_default: bool = Field(
        sa_column=sa.Column(sa.Boolean, nullable=False, server_default=sa.false())
    )
    # Decorative only — never used in any query that determines history.
    label: str | None = None

    created_at: datetime | None = created_at_column()
    updated_at: datetime | None = updated_at_column()

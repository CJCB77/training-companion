from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

from app.models.enums import ProgressionType
from app.models.timestamps import created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.exercise import Exercise
    from app.models.exercise_performance import ExercisePerformance
    from app.models.workout_session import WorkoutSession


class ExercisePrescription(SQLModel, table=True):
    __tablename__ = "exercise_prescriptions"

    id: int | None = Field(default=None, primary_key=True)
    workout_session_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("workout_sessions.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    # RESTRICT: an exercise referenced by a prescription cannot be deleted out from
    # under it.
    exercise_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("exercises.id", ondelete="RESTRICT"),
            index=True,
            nullable=False,
        )
    )
    # Every prescription belongs to exactly one ProgressionLine — eagerly
    # materialized, NOT NULL. No relationship declared toward ProgressionLine; see
    # app/models/progression_line.py for why. RESTRICT: a line with prescriptions
    # still on it cannot be deleted (line deletion isn't implemented anyway — see
    # CLAUDE.md's Progression Lines non-goals for v1).
    progression_line_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("progression_lines.id", ondelete="RESTRICT"),
            index=True,
            nullable=False,
        )
    )

    # Position of this exercise within the session.
    order_index: int

    target_sets: int
    target_reps: int
    # Nullable for bodyweight or percentage-derived prescriptions.
    target_weight: float | None = None
    target_rpe: float | None = None

    # Per-exercise override of the program's default progression. NULL = inherit the
    # program default (see Program.default_progression_*).
    progression_type: ProgressionType | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    progression_params: dict | None = Field(
        default=None, sa_column=sa.Column(JSONB, nullable=True)
    )
    notes: str | None = None

    created_at: datetime | None = created_at_column()
    updated_at: datetime | None = updated_at_column()

    workout_session: "WorkoutSession" = Relationship(back_populates="prescriptions")
    exercise: "Exercise" = Relationship(back_populates="prescriptions")
    performances: list["ExercisePerformance"] = Relationship(
        back_populates="prescription",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

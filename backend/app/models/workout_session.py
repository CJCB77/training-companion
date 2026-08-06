from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from app.models.timestamps import created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.exercise_prescription import ExercisePrescription
    from app.models.training_week import TrainingWeek


class WorkoutSession(SQLModel, table=True):
    __tablename__ = "workout_sessions"

    id: int | None = Field(default=None, primary_key=True)
    week_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("training_weeks.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    day_name: str
    # Position of this session within its week ("order" is a reserved SQL word).
    order_index: int

    # Execution state, derived (never stored as a separate status column): NULL
    # started_at = not started; started_at set, completed_at NULL = in progress;
    # both set = completed. See app/schemas/workout_sessions.py for the derived
    # `status` field exposed to clients.
    started_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )
    notes: str | None = None

    created_at: datetime | None = created_at_column()
    updated_at: datetime | None = updated_at_column()

    week: "TrainingWeek" = Relationship(back_populates="workout_sessions")
    prescriptions: list["ExercisePrescription"] = Relationship(
        back_populates="workout_session",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

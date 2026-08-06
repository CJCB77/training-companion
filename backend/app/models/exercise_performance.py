from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from app.models.enums import SetCompletionState
from app.models.timestamps import created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.exercise_prescription import ExercisePrescription


class ExercisePerformance(SQLModel, table=True):
    __tablename__ = "exercise_performances"

    id: int | None = Field(default=None, primary_key=True)
    prescription_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("exercise_prescriptions.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    # 1-based position within the prescription (set 1, set 2, ...).
    set_number: int

    actual_reps: int
    # Nullable for bodyweight work; RPE is optional per set.
    actual_weight: float | None = None
    actual_rpe: float | None = None

    completion_state: SetCompletionState = Field(
        sa_column=sa.Column(sa.String, nullable=False)
    )
    notes: str | None = None

    created_at: datetime | None = created_at_column()
    updated_at: datetime | None = updated_at_column()

    prescription: "ExercisePrescription" = Relationship(back_populates="performances")

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ProgressionType
from app.schemas.progression import ProgressionParams


class ExercisePrescriptionCreate(BaseModel):
    """`order_index` is optional — omitted, the service auto-assigns `max + 1`
    (or 0 for the session's first prescription). Workout session id comes from
    the path, never the body.
    """

    exercise_id: int
    order_index: int | None = Field(default=None, ge=0)
    target_sets: int = Field(ge=1)
    target_reps: int = Field(ge=1)
    target_weight: float | None = Field(default=None, ge=0)
    target_rpe: float | None = Field(default=None, ge=1, le=10)
    progression_type: ProgressionType | None = None
    progression_params: ProgressionParams | None = None
    notes: str | None = None


class ExercisePrescriptionUpdate(BaseModel):
    """All fields optional — only what's set is applied (partial update)."""

    exercise_id: int | None = None
    order_index: int | None = Field(default=None, ge=0)
    target_sets: int | None = Field(default=None, ge=1)
    target_reps: int | None = Field(default=None, ge=1)
    target_weight: float | None = Field(default=None, ge=0)
    target_rpe: float | None = Field(default=None, ge=1, le=10)
    progression_type: ProgressionType | None = None
    progression_params: ProgressionParams | None = None
    notes: str | None = None


class ExercisePrescriptionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    workout_session_id: int
    exercise_id: int
    order_index: int
    target_sets: int
    target_reps: int
    target_weight: float | None
    target_rpe: float | None
    progression_type: ProgressionType | None
    progression_params: dict | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

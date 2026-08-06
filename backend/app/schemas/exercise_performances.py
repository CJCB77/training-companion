from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SetCompletionState


class ExercisePerformanceCreate(BaseModel):
    """`set_number` is optional — omitted, the service auto-assigns `max + 1`
    (or 1 for the prescription's first logged set). Prescription id comes from
    the path, never the body.
    """

    set_number: int | None = Field(default=None, ge=1)
    actual_reps: int = Field(ge=0)
    actual_weight: float | None = Field(default=None, ge=0)
    actual_rpe: float | None = Field(default=None, ge=1, le=10)
    completion_state: SetCompletionState
    notes: str | None = None


class ExercisePerformanceUpdate(BaseModel):
    """All fields optional — only what's set is applied (partial update)."""

    set_number: int | None = Field(default=None, ge=1)
    actual_reps: int | None = Field(default=None, ge=0)
    actual_weight: float | None = Field(default=None, ge=0)
    actual_rpe: float | None = Field(default=None, ge=1, le=10)
    completion_state: SetCompletionState | None = None
    notes: str | None = None


class ExercisePerformanceRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    prescription_id: int
    set_number: int
    actual_reps: int
    actual_weight: float | None
    actual_rpe: float | None
    completion_state: SetCompletionState
    notes: str | None
    created_at: datetime
    updated_at: datetime

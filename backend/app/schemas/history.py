"""Read models for the /history endpoints (TRAIN-21). There is no write side here —
history is derived entirely from `ExercisePerformance` data logged through the
workout-session/exercise-performance endpoints.
"""

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import PersonalRecordKind, WeightUnit


class CompletedSessionRead(BaseModel):
    id: int
    program_id: int
    week_id: int
    day_name: str
    started_at: datetime | None
    completed_at: datetime
    notes: str | None


class PersonalRecordRead(BaseModel):
    """One lifetime PR (`GET /history/personal-records`) or one PR set within a
    specific session (`GET /history/sessions/{id}/personal-records`).

    Carries both the as-logged value and its display-unit conversion — see
    TRAIN-21's design plan, "Resolved question 2". `converted` is what lets a
    client render "137.5 kg (303.13 lb converted)" instead of presenting a
    derived number as if it were the logged one.
    """

    exercise_id: int
    exercise_name: str
    kind: PersonalRecordKind
    value: float
    recorded_unit: WeightUnit
    display_value: float
    display_unit: WeightUnit
    converted: bool
    reps: int
    performed_at: datetime
    workout_session_id: int
    program_id: int
    progression_line_id: int


class OneRmTrendPointRead(BaseModel):
    """One point on the lifetime e1RM trend for an exercise — that session's best
    estimated 1RM. Spans all of the user's programs and progression lines (see
    TRAIN-21's design plan, "Resolved question 3"); `program_id` and
    `progression_line_id` are carried on every point so a client can group,
    filter, or color by either without a second endpoint.
    """

    exercise_id: int
    exercise_name: str
    value: float
    recorded_unit: WeightUnit
    display_value: float
    display_unit: WeightUnit
    converted: bool
    reps: int
    performed_at: datetime
    workout_session_id: int
    program_id: int
    progression_line_id: int

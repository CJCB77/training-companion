"""Read models for `GET /dashboard` (TRAIN-22). There is no write side here —
the whole payload is derived from data TRAIN-18/19/20/21 already landed.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.models.enums import WeightUnit
from app.schemas.history import PersonalRecordRead

# Re-exported so a client only needs one import for the whole dashboard
# response — same PR shape TRAIN-21's /history endpoints already return.
__all__ = ["PersonalRecordRead", "DashboardRead"]


class ActiveProgramRead(BaseModel):
    id: int
    name: str
    weight_unit: WeightUnit
    start_date: date | None
    end_date: date | None
    current_week_number: int | None


class ProgramProgressCounts(BaseModel):
    sessions_completed: int
    sessions_total: int


class ProgramProgressRead(BaseModel):
    """Structural progress — has a real denominator, needs no planned dates.
    See TRAIN-22's design plan, "Resolved question 2".
    """

    program: ProgramProgressCounts
    current_week: ProgramProgressCounts


class NextWorkoutRead(BaseModel):
    """Identity only — no prescriptions, no recommended weights. See TRAIN-22's
    design plan, "Other decisions": inlining recommendations here would
    duplicate `GET /progression/exercise-prescriptions/{id}/recommendation`
    N times on the most-hit endpoint.
    """

    id: int
    week_id: int
    week_number: int
    day_name: str
    order_index: int
    status: Literal["not_started", "in_progress"]
    prescription_count: int


class ConsistencyRollingWindow(BaseModel):
    """Recency, from `completed_at`. Spans all programs, not just the active
    one — "am I showing up" isn't a per-program question.
    """

    sessions_completed_last_7_days: int
    sessions_completed_last_28_days: int
    days_since_last_session: int | None


class ConsistencyRead(BaseModel):
    """Both halves of "consistency" per TRAIN-22's design plan, Resolved
    question 2 — option C. `program_progress` mirrors the top-level
    `DashboardRead.program_progress` (same object, `null` under the same
    condition); it's repeated here so a client rendering "consistency" doesn't
    need to reach outside this block for either half.
    """

    program_progress: ProgramProgressRead | None
    rolling_window: ConsistencyRollingWindow


class ExerciseTrendRead(BaseModel):
    """One exercise trained in the recent window. `best_one_rm_before_window`
    and `delta` are `None` when the exercise has no weighted history before the
    window (first time trained). Display-unit only — see TRAIN-22's design
    plan, "Other decisions": a delta between two efforts logged in different
    units has no single as-logged form.
    """

    exercise_id: int
    exercise_name: str
    best_one_rm_in_window: float
    best_one_rm_before_window: float | None
    delta: float | None
    display_unit: WeightUnit


class DashboardRead(BaseModel):
    active_program: ActiveProgramRead | None
    program_progress: ProgramProgressRead | None
    next_workout: NextWorkoutRead | None
    program_complete: bool
    consistency: ConsistencyRead
    recent_personal_records: list[PersonalRecordRead]
    exercise_trends: list[ExerciseTrendRead]

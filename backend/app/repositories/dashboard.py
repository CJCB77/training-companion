"""Read-only queries backing `GET /dashboard` (TRAIN-22).

Every query here narrows/aggregates rows only — no PR detection, no e1RM math.
That reduction is `app/services/dashboard.py`'s job, same split
`app/repositories/history.py` documents for TRAIN-21.
"""

from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.exercise_prescription import ExercisePrescription
from app.models.program import Program
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession


def list_program_sessions(
    session: Session, *, program_id: int
) -> list[tuple[WorkoutSession, int, int]]:
    """Every session in `program_id`, each paired with its week number and its
    prescription count, ordered `(week_number, order_index, id)` — the
    deterministic order TRAIN-22's design plan requires for next-workout
    resolution ("never order on a non-unique key alone").

    `program_id` is trusted as already-owned by the caller (the service fetches
    it via `programs_repo.get_active_program`, itself scoped to `user_id`), so
    this doesn't repeat a `Program.user_id` join.

    The prescription count is a `LEFT JOIN` + `COUNT`, not a per-session follow-up
    query — a program is on the order of tens of sessions, so this stays a single
    round trip regardless of program size.
    """
    statement = (
        select(
            WorkoutSession,
            TrainingWeek.week_number,
            func.count(ExercisePrescription.id),
        )
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .outerjoin(
            ExercisePrescription,
            ExercisePrescription.workout_session_id == WorkoutSession.id,  # type: ignore[arg-type]
        )
        .where(TrainingWeek.program_id == program_id)
        .group_by(WorkoutSession.id, TrainingWeek.week_number)  # type: ignore[arg-type]
        .order_by(
            TrainingWeek.week_number,
            WorkoutSession.order_index,
            WorkoutSession.id,
        )
    )
    return list(session.exec(statement).all())  # type: ignore[return-value]


def list_completed_at_since(
    session: Session, *, user_id: int, since: datetime
) -> list[datetime]:
    """`completed_at` for every session the user completed on or after `since`,
    across **all** of their programs (active or not, archived or not — "am I
    showing up" isn't a per-program question, see TRAIN-22's design plan).

    Deliberately un-ordered/unlimited: the recent window is small (28 days by
    default), so the caller reduces this list in Python (7-day count is a
    subset of the 28-day list already fetched) rather than issuing a second
    query per window.
    """
    statement = (
        select(WorkoutSession.completed_at)
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .join(Program, TrainingWeek.program_id == Program.id)  # type: ignore[arg-type]
        .where(
            Program.user_id == user_id,
            WorkoutSession.completed_at.is_not(None),  # type: ignore[union-attr]
            WorkoutSession.completed_at >= since,  # type: ignore[operator]
        )
    )
    return list(session.exec(statement).all())  # type: ignore[return-value]


def get_last_completed_at(session: Session, *, user_id: int) -> datetime | None:
    """The most recent `completed_at` across all of the user's programs,
    regardless of the recent window — so `days_since_last_session` still
    reports correctly even when nothing was completed in the last 28 days.
    """
    statement = (
        select(WorkoutSession.completed_at)
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .join(Program, TrainingWeek.program_id == Program.id)  # type: ignore[arg-type]
        .where(
            Program.user_id == user_id,
            WorkoutSession.completed_at.is_not(None),  # type: ignore[union-attr]
        )
        .order_by(WorkoutSession.completed_at.desc())  # type: ignore[union-attr]
        .limit(1)
    )
    return session.exec(statement).first()


def list_recent_exercise_ids(
    session: Session, *, user_id: int, since: datetime
) -> list[int]:
    """Distinct exercise ids trained (prescribed on a session completed on or
    after `since`) across all of the user's programs. Feeds both the recent-PR
    and exercise-trend blocks — one coherent exercise set for both, per
    TRAIN-22's design plan.
    """
    statement = (
        select(ExercisePrescription.exercise_id)
        .join(
            WorkoutSession,
            ExercisePrescription.workout_session_id == WorkoutSession.id,  # type: ignore[arg-type]
        )
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .join(Program, TrainingWeek.program_id == Program.id)  # type: ignore[arg-type]
        .where(
            Program.user_id == user_id,
            WorkoutSession.completed_at.is_not(None),  # type: ignore[union-attr]
            WorkoutSession.completed_at >= since,  # type: ignore[operator]
        )
        .distinct()
    )
    return list(session.exec(statement).all())

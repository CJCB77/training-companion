from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models.program import Program
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession


def create_workout_session(
    session: Session, *, week_id: int, day_name: str, order_index: int
) -> WorkoutSession:
    workout_session = WorkoutSession(
        week_id=week_id, day_name=day_name, order_index=order_index
    )
    session.add(workout_session)
    session.commit()
    session.refresh(workout_session)
    return workout_session


def get_workout_session(
    session: Session, workout_session_id: int
) -> WorkoutSession | None:
    return session.get(WorkoutSession, workout_session_id)


def get_workout_session_with_owner(
    session: Session, workout_session_id: int
) -> tuple[WorkoutSession, int] | None:
    """The workout session together with its owning program's `user_id`, in one
    joined query (session -> week -> program).
    """
    statement = (
        select(WorkoutSession, Program.user_id)
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .join(Program, TrainingWeek.program_id == Program.id)  # type: ignore[arg-type]
        .where(WorkoutSession.id == workout_session_id)
    )
    return session.exec(statement).first()  # type: ignore[return-value]


def list_workout_sessions_for_week(
    session: Session, week_id: int
) -> list[WorkoutSession]:
    statement = (
        select(WorkoutSession)
        .where(WorkoutSession.week_id == week_id)
        .order_by(WorkoutSession.order_index, WorkoutSession.id)  # type: ignore[arg-type]
    )
    return list(session.exec(statement).all())


def get_max_order_index(session: Session, week_id: int) -> int | None:
    return session.exec(
        select(WorkoutSession.order_index)
        .where(WorkoutSession.week_id == week_id)
        .order_by(WorkoutSession.order_index.desc())  # type: ignore[union-attr]
        .limit(1)
    ).first()


# Fields callers are allowed to change via update_workout_session. An explicit
# allow-list keeps id/week_id from being mass-assigned, same as
# programs_repo.update_program.
_UPDATABLE_FIELDS = {"day_name", "order_index"}


def update_workout_session(
    session: Session, workout_session: WorkoutSession, **fields: Any
) -> WorkoutSession:
    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"update_workout_session cannot set fields: {sorted(unknown)}")
    for key, value in fields.items():
        setattr(workout_session, key, value)
    session.add(workout_session)
    session.commit()
    session.refresh(workout_session)
    return workout_session


def delete_workout_session(session: Session, workout_session: WorkoutSession) -> None:
    """Permanently remove a workout session and its owned ExercisePrescriptions
    (cascade via the ORM/DB relationships already configured).
    """
    session.delete(workout_session)
    session.commit()


def start_workout_session(
    session: Session, workout_session: WorkoutSession
) -> WorkoutSession:
    """Mark a session in-progress. Idempotent: if already started, the existing
    started_at timestamp is left alone so "when was this started" stays stable.
    """
    if workout_session.started_at is None:
        workout_session.started_at = datetime.now(timezone.utc)
    session.add(workout_session)
    session.commit()
    session.refresh(workout_session)
    return workout_session


def complete_workout_session(
    session: Session, workout_session: WorkoutSession
) -> WorkoutSession:
    """Mark a session complete. Idempotent: if already completed, the existing
    completed_at timestamp is left alone.
    """
    if workout_session.completed_at is None:
        workout_session.completed_at = datetime.now(timezone.utc)
    session.add(workout_session)
    session.commit()
    session.refresh(workout_session)
    return workout_session

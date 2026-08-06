from typing import Any

from sqlmodel import Session, select

from app.models.exercise_performance import ExercisePerformance
from app.models.exercise_prescription import ExercisePrescription
from app.models.program import Program
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession


def create_exercise_performance(
    session: Session,
    *,
    prescription_id: int,
    set_number: int,
    actual_reps: int,
    completion_state: str,
    actual_weight: float | None = None,
    actual_rpe: float | None = None,
    notes: str | None = None,
) -> ExercisePerformance:
    performance = ExercisePerformance(
        prescription_id=prescription_id,
        set_number=set_number,
        actual_reps=actual_reps,
        actual_weight=actual_weight,
        actual_rpe=actual_rpe,
        completion_state=completion_state,
        notes=notes,
    )
    session.add(performance)
    session.commit()
    session.refresh(performance)
    return performance


def get_exercise_performance(
    session: Session, performance_id: int
) -> ExercisePerformance | None:
    return session.get(ExercisePerformance, performance_id)


def get_exercise_performance_with_owner(
    session: Session, performance_id: int
) -> tuple[ExercisePerformance, int] | None:
    """The performance together with its owning program's `user_id`, in one
    joined query (performance -> prescription -> session -> week -> program).
    """
    statement = (
        select(ExercisePerformance, Program.user_id)
        .join(
            ExercisePrescription,
            ExercisePerformance.prescription_id == ExercisePrescription.id,  # type: ignore[arg-type]
        )
        .join(
            WorkoutSession,
            ExercisePrescription.workout_session_id == WorkoutSession.id,  # type: ignore[arg-type]
        )
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .join(Program, TrainingWeek.program_id == Program.id)  # type: ignore[arg-type]
        .where(ExercisePerformance.id == performance_id)
    )
    return session.exec(statement).first()  # type: ignore[return-value]


def list_performances_for_prescription(
    session: Session, prescription_id: int
) -> list[ExercisePerformance]:
    statement = (
        select(ExercisePerformance)
        .where(ExercisePerformance.prescription_id == prescription_id)
        .order_by(ExercisePerformance.set_number, ExercisePerformance.id)  # type: ignore[arg-type]
    )
    return list(session.exec(statement).all())


def list_performances_for_session(
    session: Session, workout_session_id: int
) -> list[ExercisePerformance]:
    statement = (
        select(ExercisePerformance)
        .join(
            ExercisePrescription,
            ExercisePerformance.prescription_id == ExercisePrescription.id,  # type: ignore[arg-type]
        )
        .where(ExercisePrescription.workout_session_id == workout_session_id)
        .order_by(
            ExercisePrescription.order_index,
            ExercisePerformance.set_number,
            ExercisePerformance.id,
        )
    )
    return list(session.exec(statement).all())


def get_max_set_number(session: Session, prescription_id: int) -> int | None:
    return session.exec(
        select(ExercisePerformance.set_number)
        .where(ExercisePerformance.prescription_id == prescription_id)
        .order_by(ExercisePerformance.set_number.desc())  # type: ignore[union-attr]
        .limit(1)
    ).first()


# Fields callers are allowed to change via update_exercise_performance. An
# explicit allow-list keeps id/prescription_id from being mass-assigned, same
# as exercise_prescriptions_repo.update_exercise_prescription.
_UPDATABLE_FIELDS = {
    "set_number",
    "actual_reps",
    "actual_weight",
    "actual_rpe",
    "completion_state",
    "notes",
}


def update_exercise_performance(
    session: Session, performance: ExercisePerformance, **fields: Any
) -> ExercisePerformance:
    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(
            f"update_exercise_performance cannot set fields: {sorted(unknown)}"
        )
    for key, value in fields.items():
        setattr(performance, key, value)
    session.add(performance)
    session.commit()
    session.refresh(performance)
    return performance


def delete_exercise_performance(
    session: Session, performance: ExercisePerformance
) -> None:
    session.delete(performance)
    session.commit()

from collections import defaultdict
from typing import Any

from sqlmodel import Session, select

from app.models.enums import ProgressionType
from app.models.exercise_performance import ExercisePerformance
from app.models.exercise_prescription import ExercisePrescription
from app.models.program import Program
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession


def create_exercise_prescription(
    session: Session,
    *,
    workout_session_id: int,
    exercise_id: int,
    order_index: int,
    target_sets: int,
    target_reps: int,
    target_weight: float | None = None,
    target_rpe: float | None = None,
    progression_type: ProgressionType | None = None,
    progression_params: dict | None = None,
    notes: str | None = None,
) -> ExercisePrescription:
    prescription = ExercisePrescription(
        workout_session_id=workout_session_id,
        exercise_id=exercise_id,
        order_index=order_index,
        target_sets=target_sets,
        target_reps=target_reps,
        target_weight=target_weight,
        target_rpe=target_rpe,
        progression_type=progression_type,
        progression_params=progression_params,
        notes=notes,
    )
    session.add(prescription)
    session.commit()
    session.refresh(prescription)
    return prescription


def get_exercise_prescription(
    session: Session, prescription_id: int
) -> ExercisePrescription | None:
    return session.get(ExercisePrescription, prescription_id)


def get_exercise_prescription_with_owner(
    session: Session, prescription_id: int
) -> tuple[ExercisePrescription, int] | None:
    """The prescription together with its owning program's `user_id`, in one
    joined query (prescription -> session -> week -> program).
    """
    statement = (
        select(ExercisePrescription, Program.user_id)
        .join(
            WorkoutSession,
            ExercisePrescription.workout_session_id == WorkoutSession.id,  # type: ignore[arg-type]
        )
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .join(Program, TrainingWeek.program_id == Program.id)  # type: ignore[arg-type]
        .where(ExercisePrescription.id == prescription_id)
    )
    return session.exec(statement).first()  # type: ignore[return-value]


def list_exercise_prescriptions_for_session(
    session: Session, workout_session_id: int
) -> list[ExercisePrescription]:
    statement = (
        select(ExercisePrescription)
        .where(ExercisePrescription.workout_session_id == workout_session_id)
        .order_by(ExercisePrescription.order_index, ExercisePrescription.id)  # type: ignore[arg-type]
    )
    return list(session.exec(statement).all())


def get_max_order_index(session: Session, workout_session_id: int) -> int | None:
    return session.exec(
        select(ExercisePrescription.order_index)
        .where(ExercisePrescription.workout_session_id == workout_session_id)
        .order_by(ExercisePrescription.order_index.desc())  # type: ignore[union-attr]
        .limit(1)
    ).first()


# Fields callers are allowed to change via update_exercise_prescription. An
# explicit allow-list keeps id/workout_session_id from being mass-assigned, same
# as programs_repo.update_program.
_UPDATABLE_FIELDS = {
    "exercise_id",
    "order_index",
    "target_sets",
    "target_reps",
    "target_weight",
    "target_rpe",
    "progression_type",
    "progression_params",
    "notes",
}


def update_exercise_prescription(
    session: Session, prescription: ExercisePrescription, **fields: Any
) -> ExercisePrescription:
    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(
            f"update_exercise_prescription cannot set fields: {sorted(unknown)}"
        )
    for key, value in fields.items():
        setattr(prescription, key, value)
    session.add(prescription)
    session.commit()
    session.refresh(prescription)
    return prescription


def delete_exercise_prescription(
    session: Session, prescription: ExercisePrescription
) -> None:
    session.delete(prescription)
    session.commit()


def list_prior_attempts(
    session: Session,
    *,
    program_id: int,
    exercise_id: int,
    limit: int,
) -> list[tuple[ExercisePrescription, list[ExercisePerformance]]]:
    """Prior prescriptions of `exercise_id` within `program_id` whose session was
    completed, newest first (by `WorkoutSession.completed_at`), each paired with its
    logged performances.

    Two queries total, not N+1: the prescriptions (with the same prescription ->
    session -> week -> program join chain already used by
    `exercise_performances_repo.get_exercise_performance_with_owner`), then their
    performances fetched in one follow-up query keyed by prescription id.
    """
    prescriptions_statement = (
        select(ExercisePrescription)
        .join(
            WorkoutSession,
            ExercisePrescription.workout_session_id == WorkoutSession.id,  # type: ignore[arg-type]
        )
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .where(
            TrainingWeek.program_id == program_id,
            ExercisePrescription.exercise_id == exercise_id,
            WorkoutSession.completed_at.is_not(None),  # type: ignore[union-attr]
        )
        .order_by(WorkoutSession.completed_at.desc())  # type: ignore[union-attr]
        .limit(limit)
    )
    prescriptions = list(session.exec(prescriptions_statement).all())
    if not prescriptions:
        return []

    prescription_ids = [p.id for p in prescriptions]
    performances_statement = select(ExercisePerformance).where(
        ExercisePerformance.prescription_id.in_(prescription_ids)  # type: ignore[attr-defined]
    )
    performances_by_prescription: dict[int, list[ExercisePerformance]] = defaultdict(
        list
    )
    for performance in session.exec(performances_statement).all():
        performances_by_prescription[performance.prescription_id].append(performance)

    return [
        (prescription, performances_by_prescription.get(prescription.id, []))
        for prescription in prescriptions
    ]

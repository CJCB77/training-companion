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
    progression_line_id: int,
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
        progression_line_id=progression_line_id,
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


def list_exercise_prescriptions_for_sessions(
    session: Session, session_ids: list[int]
) -> list[ExercisePrescription]:
    """Flat `in_()` read across multiple sessions, ordered
    `workout_session_id, order_index` — same shape `programs_repo.duplicate_program_tree`
    already uses for its prescriptions read. Empty input short-circuits to an empty
    result rather than emitting a query with an empty `IN (...)`.
    """
    if not session_ids:
        return []
    statement = (
        select(ExercisePrescription)
        .where(ExercisePrescription.workout_session_id.in_(session_ids))  # type: ignore[attr-defined]
        .order_by(
            ExercisePrescription.workout_session_id,
            ExercisePrescription.order_index,  # type: ignore[arg-type]
        )
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


def update_exercise_prescription_with_progression_line(
    session: Session,
    prescription: ExercisePrescription,
    *,
    progression_line_id: int,
    **fields: Any,
) -> ExercisePrescription:
    """Sets `progression_line_id` directly (bypassing `_UPDATABLE_FIELDS`) together
    with any other prescription fields (typically `exercise_id`), in a single
    add/commit.

    Single-transaction is the point: when `exercise_id` changes on a default-line
    prescription, the service re-resolves the new exercise's default line and both
    writes must land together. Two separate commits (write `exercise_id`, then
    write `progression_line_id`) would leave a window where a failure between them
    permanently commits a prescription whose `exercise_id` disagrees with its
    `progression_line.exercise_id` — exactly the invariant this ticket exists to
    protect, with nothing to detect or repair it after the fact.

    `fields` still goes through the same `_UPDATABLE_FIELDS` allow-list as
    `update_exercise_prescription`; only `progression_line_id` bypasses it, since
    that allow-list deliberately excludes it — a user cannot re-assign a
    prescription to a different *existing* line (a ticket non-goal). This function
    is a distinct, purpose-built path: the service's automatic re-resolution
    to the new exercise's default line when `exercise_id` changes on a
    default-line prescription. Mirrors `programs_repo.archive_program`/
    `unarchive_program` setting `archived_at` directly rather than through the
    generic `update_program`.
    """
    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(
            "update_exercise_prescription_with_progression_line cannot set "
            f"fields: {sorted(unknown)}"
        )
    for key, value in fields.items():
        setattr(prescription, key, value)
    prescription.progression_line_id = progression_line_id
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
    progression_line_id: int,
    limit: int,
) -> list[tuple[ExercisePrescription, list[ExercisePerformance]]]:
    """Prior prescriptions on `progression_line_id` (the exercise's progression line
    within `program_id` — see CLAUDE.md's "Progression Lines") whose session was
    completed, newest first (by `WorkoutSession.completed_at`), each paired with its
    logged performances.

    Every `ExercisePrescription.progression_line_id` is populated from creation
    onward (NOT NULL) — there is no NULL-means-default convention to special-case
    here, so plain equality is all scoping needs; `IS NOT DISTINCT FROM` is not
    required. `program_id`/`exercise_id` are kept as extra predicates even though
    `progression_line_id` alone already identifies the history set (a line is
    already program- and exercise-scoped) — they cost nothing on an indexed join
    and turn any future data inconsistency into an empty result rather than a
    silently wrong recommendation.

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
            ExercisePrescription.progression_line_id == progression_line_id,
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

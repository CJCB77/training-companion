"""ExercisePerformance CRUD business logic: ownership enforcement and
set_number assignment live here, not in the routes.

Routes only translate these exceptions into HTTP responses. Logging endpoints
are deliberately simple/fast (single writes, no cross-row validation against
target_sets) per CLAUDE.md's #1 UX priority — frictionless workout logging.
"""

from sqlmodel import Session

from app.models.exercise_performance import ExercisePerformance
from app.repositories import exercise_performances as exercise_performances_repo
from app.schemas.exercise_performances import (
    ExercisePerformanceCreate,
    ExercisePerformanceUpdate,
)
from app.services import exercise_prescriptions as exercise_prescriptions_service
from app.services import workout_sessions as workout_sessions_service


class ExercisePerformanceNotFoundError(Exception):
    """No exercise performance exists with that id."""


class ExercisePerformanceAccessDeniedError(Exception):
    """The performance exists but its program belongs to a different user."""


class InvalidExercisePerformanceUpdateError(Exception):
    """A required (non-nullable) field was explicitly set to null."""


# Columns that are NOT NULL at the DB level — an explicit `null` for one of
# these in a partial update must be rejected as a 422, not left to reach the
# DB and raise an uncaught IntegrityError (500).
_NON_NULLABLE_UPDATE_FIELDS = {"set_number", "actual_reps", "completion_state"}


def _reject_null_updates(updates: dict) -> None:
    nulled = [
        field
        for field in _NON_NULLABLE_UPDATE_FIELDS
        if field in updates and updates[field] is None
    ]
    if nulled:
        raise InvalidExercisePerformanceUpdateError(
            f"{', '.join(sorted(nulled))} cannot be null"
        )


def get_owned_exercise_performance(
    session: Session, *, user_id: int, performance_id: int
) -> ExercisePerformance:
    """Fetch a performance whose program the caller owns, or raise.

    Not-found and access-denied are kept as distinct exceptions for callers that
    care, but the API layer maps both to 404 so a non-owner can't learn a
    performance id exists.
    """
    result = exercise_performances_repo.get_exercise_performance_with_owner(
        session, performance_id
    )
    if result is None:
        raise ExercisePerformanceNotFoundError(performance_id)
    performance, owner_user_id = result
    if owner_user_id != user_id:
        raise ExercisePerformanceAccessDeniedError(performance_id)
    return performance


def list_performances_for_prescription(
    session: Session, *, user_id: int, prescription_id: int
) -> list[ExercisePerformance]:
    # Raises ExercisePrescriptionNotFoundError/ExercisePrescriptionAccessDeniedError
    # if the caller doesn't own the parent prescription — the route maps those
    # to 404 too.
    exercise_prescriptions_service.get_owned_exercise_prescription(
        session, user_id=user_id, prescription_id=prescription_id
    )
    return exercise_performances_repo.list_performances_for_prescription(
        session, prescription_id
    )


def list_performances_for_session(
    session: Session, *, user_id: int, workout_session_id: int
) -> list[ExercisePerformance]:
    # Raises WorkoutSessionNotFoundError/WorkoutSessionAccessDeniedError if the
    # caller doesn't own the session — the route maps those to 404 too.
    workout_sessions_service.get_owned_workout_session(
        session, user_id=user_id, workout_session_id=workout_session_id
    )
    return exercise_performances_repo.list_performances_for_session(
        session, workout_session_id
    )


def create_exercise_performance_for_prescription(
    session: Session,
    *,
    user_id: int,
    prescription_id: int,
    payload: ExercisePerformanceCreate,
) -> ExercisePerformance:
    exercise_prescriptions_service.get_owned_exercise_prescription(
        session, user_id=user_id, prescription_id=prescription_id
    )

    set_number = payload.set_number
    if set_number is None:
        max_set_number = exercise_performances_repo.get_max_set_number(
            session, prescription_id
        )
        set_number = 1 if max_set_number is None else max_set_number + 1

    return exercise_performances_repo.create_exercise_performance(
        session,
        prescription_id=prescription_id,
        set_number=set_number,
        actual_reps=payload.actual_reps,
        actual_weight=payload.actual_weight,
        actual_rpe=payload.actual_rpe,
        completion_state=payload.completion_state,
        notes=payload.notes,
    )


def update_exercise_performance(
    session: Session,
    *,
    user_id: int,
    performance_id: int,
    payload: ExercisePerformanceUpdate,
) -> ExercisePerformance:
    performance = get_owned_exercise_performance(
        session, user_id=user_id, performance_id=performance_id
    )
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return performance
    _reject_null_updates(updates)
    return exercise_performances_repo.update_exercise_performance(
        session, performance, **updates
    )


def delete_exercise_performance(
    session: Session, *, user_id: int, performance_id: int
) -> None:
    performance = get_owned_exercise_performance(
        session, user_id=user_id, performance_id=performance_id
    )
    exercise_performances_repo.delete_exercise_performance(session, performance)

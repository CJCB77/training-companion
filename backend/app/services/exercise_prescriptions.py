"""ExercisePrescription CRUD business logic: ownership enforcement, order_index
assignment, and exercise-visibility checks live here, not in the routes.

Routes only translate these exceptions into HTTP responses.
"""

from sqlmodel import Session

from app.models.exercise_prescription import ExercisePrescription
from app.repositories import exercise_prescriptions as exercise_prescriptions_repo
from app.repositories import exercises as exercises_repo
from app.schemas.exercise_prescriptions import (
    ExercisePrescriptionCreate,
    ExercisePrescriptionUpdate,
)
from app.services import workout_sessions as workout_sessions_service


class ExercisePrescriptionNotFoundError(Exception):
    """No exercise prescription exists with that id."""


class ExercisePrescriptionAccessDeniedError(Exception):
    """The prescription exists but its program belongs to a different user."""


class ExerciseNotVisibleError(Exception):
    """The referenced exercise doesn't exist or isn't visible to this user."""


class InvalidExercisePrescriptionUpdateError(Exception):
    """A required (non-nullable) field was explicitly set to null."""


# Columns that are NOT NULL at the DB level — an explicit `null` for one of
# these in a partial update must be rejected as a 422, not left to reach the
# DB and raise an uncaught IntegrityError (500), or in exercise_id's case,
# fall through to get_visible_exercise and raise a misleading "Exercise not
# found" 404 for a request that never named an exercise at all.
_NON_NULLABLE_UPDATE_FIELDS = {
    "exercise_id",
    "order_index",
    "target_sets",
    "target_reps",
}


def _reject_null_updates(updates: dict) -> None:
    nulled = [
        field
        for field in _NON_NULLABLE_UPDATE_FIELDS
        if field in updates and updates[field] is None
    ]
    if nulled:
        raise InvalidExercisePrescriptionUpdateError(
            f"{', '.join(sorted(nulled))} cannot be null"
        )


def get_owned_exercise_prescription(
    session: Session, *, user_id: int, prescription_id: int
) -> ExercisePrescription:
    """Fetch a prescription whose program the caller owns, or raise.

    Not-found and access-denied are kept as distinct exceptions for callers that
    care, but the API layer maps both to 404 so a non-owner can't learn a
    prescription id exists.
    """
    result = exercise_prescriptions_repo.get_exercise_prescription_with_owner(
        session, prescription_id
    )
    if result is None:
        raise ExercisePrescriptionNotFoundError(prescription_id)
    prescription, owner_user_id = result
    if owner_user_id != user_id:
        raise ExercisePrescriptionAccessDeniedError(prescription_id)
    return prescription


def list_exercise_prescriptions(
    session: Session, *, user_id: int, workout_session_id: int
) -> list[ExercisePrescription]:
    # Raises WorkoutSessionNotFoundError/WorkoutSessionAccessDeniedError if the
    # caller doesn't own the parent session — the route maps those to 404 too.
    workout_sessions_service.get_owned_workout_session(
        session, user_id=user_id, workout_session_id=workout_session_id
    )
    return exercise_prescriptions_repo.list_exercise_prescriptions_for_session(
        session, workout_session_id
    )


def create_exercise_prescription_for_session(
    session: Session,
    *,
    user_id: int,
    workout_session_id: int,
    payload: ExercisePrescriptionCreate,
) -> ExercisePrescription:
    workout_sessions_service.get_owned_workout_session(
        session, user_id=user_id, workout_session_id=workout_session_id
    )

    exercise = exercises_repo.get_visible_exercise(
        session, user_id=user_id, exercise_id=payload.exercise_id
    )
    if exercise is None:
        raise ExerciseNotVisibleError(payload.exercise_id)

    order_index = payload.order_index
    if order_index is None:
        max_order_index = exercise_prescriptions_repo.get_max_order_index(
            session, workout_session_id
        )
        order_index = 0 if max_order_index is None else max_order_index + 1

    return exercise_prescriptions_repo.create_exercise_prescription(
        session,
        workout_session_id=workout_session_id,
        exercise_id=payload.exercise_id,
        order_index=order_index,
        target_sets=payload.target_sets,
        target_reps=payload.target_reps,
        target_weight=payload.target_weight,
        target_rpe=payload.target_rpe,
        progression_type=payload.progression_type,
        progression_params=payload.progression_params,
        notes=payload.notes,
    )


def update_exercise_prescription(
    session: Session,
    *,
    user_id: int,
    prescription_id: int,
    payload: ExercisePrescriptionUpdate,
) -> ExercisePrescription:
    prescription = get_owned_exercise_prescription(
        session, user_id=user_id, prescription_id=prescription_id
    )
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return prescription
    _reject_null_updates(updates)

    if "exercise_id" in updates:
        exercise = exercises_repo.get_visible_exercise(
            session, user_id=user_id, exercise_id=updates["exercise_id"]
        )
        if exercise is None:
            raise ExerciseNotVisibleError(updates["exercise_id"])

    return exercise_prescriptions_repo.update_exercise_prescription(
        session, prescription, **updates
    )


def delete_exercise_prescription(
    session: Session, *, user_id: int, prescription_id: int
) -> None:
    prescription = get_owned_exercise_prescription(
        session, user_id=user_id, prescription_id=prescription_id
    )
    exercise_prescriptions_repo.delete_exercise_prescription(session, prescription)

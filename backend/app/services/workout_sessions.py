"""WorkoutSession CRUD business logic: ownership enforcement and order_index
assignment live here, not in the routes.

Routes only translate these exceptions into HTTP responses.
"""

from sqlmodel import Session

from app.models.workout_session import WorkoutSession
from app.repositories import workout_sessions as workout_sessions_repo
from app.schemas.workout_sessions import WorkoutSessionCreate, WorkoutSessionUpdate
from app.services import training_weeks as training_weeks_service


class WorkoutSessionNotFoundError(Exception):
    """No workout session exists with that id."""


class WorkoutSessionAccessDeniedError(Exception):
    """The workout session exists but its program belongs to a different user."""


class InvalidWorkoutSessionUpdateError(Exception):
    """A required (non-nullable) field was explicitly set to null."""


# Columns that are NOT NULL at the DB level — an explicit `null` for one of
# these in a partial update must be rejected as a 422, not left to reach the
# DB and raise an uncaught IntegrityError (500).
_NON_NULLABLE_UPDATE_FIELDS = {"day_name", "order_index"}


def _reject_null_updates(updates: dict) -> None:
    nulled = [
        field
        for field in _NON_NULLABLE_UPDATE_FIELDS
        if field in updates and updates[field] is None
    ]
    if nulled:
        raise InvalidWorkoutSessionUpdateError(
            f"{', '.join(sorted(nulled))} cannot be null"
        )


def get_owned_workout_session(
    session: Session, *, user_id: int, workout_session_id: int
) -> WorkoutSession:
    """Fetch a workout session whose program the caller owns, or raise.

    Not-found and access-denied are kept as distinct exceptions for callers that
    care, but the API layer maps both to 404 so a non-owner can't learn a session
    id exists.
    """
    result = workout_sessions_repo.get_workout_session_with_owner(
        session, workout_session_id
    )
    if result is None:
        raise WorkoutSessionNotFoundError(workout_session_id)
    workout_session, owner_user_id = result
    if owner_user_id != user_id:
        raise WorkoutSessionAccessDeniedError(workout_session_id)
    return workout_session


def list_workout_sessions(
    session: Session, *, user_id: int, week_id: int
) -> list[WorkoutSession]:
    # Raises TrainingWeekNotFoundError/TrainingWeekAccessDeniedError if the
    # caller doesn't own the parent week — the route maps those to 404 too.
    training_weeks_service.get_owned_training_week(
        session, user_id=user_id, week_id=week_id
    )
    return workout_sessions_repo.list_workout_sessions_for_week(session, week_id)


def create_workout_session_for_week(
    session: Session, *, user_id: int, week_id: int, payload: WorkoutSessionCreate
) -> WorkoutSession:
    training_weeks_service.get_owned_training_week(
        session, user_id=user_id, week_id=week_id
    )

    order_index = payload.order_index
    if order_index is None:
        max_order_index = workout_sessions_repo.get_max_order_index(session, week_id)
        order_index = 0 if max_order_index is None else max_order_index + 1

    return workout_sessions_repo.create_workout_session(
        session, week_id=week_id, day_name=payload.day_name, order_index=order_index
    )


def update_workout_session(
    session: Session,
    *,
    user_id: int,
    workout_session_id: int,
    payload: WorkoutSessionUpdate,
) -> WorkoutSession:
    workout_session = get_owned_workout_session(
        session, user_id=user_id, workout_session_id=workout_session_id
    )
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return workout_session
    _reject_null_updates(updates)
    return workout_sessions_repo.update_workout_session(
        session, workout_session, **updates
    )


def delete_workout_session(
    session: Session, *, user_id: int, workout_session_id: int
) -> None:
    workout_session = get_owned_workout_session(
        session, user_id=user_id, workout_session_id=workout_session_id
    )
    workout_sessions_repo.delete_workout_session(session, workout_session)


def start_workout_session(
    session: Session, *, user_id: int, workout_session_id: int
) -> WorkoutSession:
    workout_session = get_owned_workout_session(
        session, user_id=user_id, workout_session_id=workout_session_id
    )
    return workout_sessions_repo.start_workout_session(session, workout_session)


def complete_workout_session(
    session: Session, *, user_id: int, workout_session_id: int
) -> WorkoutSession:
    workout_session = get_owned_workout_session(
        session, user_id=user_id, workout_session_id=workout_session_id
    )
    return workout_sessions_repo.complete_workout_session(session, workout_session)

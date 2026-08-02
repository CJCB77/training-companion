"""Exercise listing and custom-exercise creation business logic.

Routes only translate these exceptions into HTTP responses.
"""

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models.enums import ExerciseCategory, MuscleGroup
from app.models.exercise import Exercise
from app.repositories import exercises as exercises_repo
from app.schemas.exercises import ExerciseCreate


class DuplicateExerciseNameError(Exception):
    """An exercise with this name is already visible to this user."""


def list_exercises(
    session: Session,
    *,
    user_id: int,
    search: str | None = None,
    muscle_group: MuscleGroup | None = None,
    category: ExerciseCategory | None = None,
) -> list[Exercise]:
    normalized_search = search.strip() if search else None
    return exercises_repo.list_exercises(
        session,
        user_id,
        muscle_group=muscle_group,
        search=normalized_search or None,
        category=category,
    )


def create_custom_exercise(
    session: Session, *, user_id: int, payload: ExerciseCreate
) -> Exercise:
    """Create a custom exercise owned by `user_id`.

    The name check below is an early, friendly rejection for the common case, but
    it's a check-then-act with no atomicity — two concurrent requests for the same
    name can both pass it before either commits. `uq_exercise_user_name` is the
    actual guarantee; the except clause turns its violation into the same error.
    """
    existing = exercises_repo.find_visible_exercise_by_name(
        session, user_id=user_id, name=payload.name
    )
    if existing is not None:
        raise DuplicateExerciseNameError(payload.name)
    try:
        return exercises_repo.create_exercise(
            session,
            name=payload.name,
            muscle_group=payload.muscle_group,
            equipment=payload.equipment,
            created_by_user_id=user_id,
            description=payload.description,
            category=payload.category,
            icon=payload.icon,
            image_url=payload.image_url,
            video_url=payload.video_url,
        )
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateExerciseNameError(payload.name) from exc

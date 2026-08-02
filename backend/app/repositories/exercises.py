from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from app.models.enums import Equipment, ExerciseCategory, MuscleGroup
from app.models.exercise import Exercise


def _visible_to_user(user_id: int):
    """System exercises OR the caller's own custom ones.

    A user never sees another user's custom exercises.
    """
    return or_(
        Exercise.created_by_user_id.is_(None),  # type: ignore[union-attr]
        Exercise.created_by_user_id == user_id,
    )


def list_exercises(
    session: Session,
    user_id: int,
    muscle_group: MuscleGroup | None = None,
    search: str | None = None,
    category: ExerciseCategory | None = None,
) -> list[Exercise]:
    """System exercises plus the caller's own custom ones, ordered by name.

    A user never sees another user's custom exercises. `search`, `muscle_group`, and
    `category` filters compose with AND when given.
    """
    statement = select(Exercise).where(_visible_to_user(user_id))
    if muscle_group is not None:
        statement = statement.where(Exercise.muscle_group == muscle_group)
    if search is not None:
        statement = statement.where(col(Exercise.name).ilike(f"%{search}%"))
    if category is not None:
        statement = statement.where(Exercise.category == category)
    statement = statement.order_by(Exercise.name)
    return list(session.exec(statement).all())


def find_visible_exercise_by_name(
    session: Session, *, user_id: int, name: str
) -> Exercise | None:
    """The system or own-custom exercise whose name case-insensitively matches `name`."""
    statement = select(Exercise).where(
        _visible_to_user(user_id),
        func.lower(Exercise.name) == name.strip().lower(),
    )
    return session.exec(statement).first()


def get_exercise(session: Session, exercise_id: int) -> Exercise | None:
    return session.get(Exercise, exercise_id)


def create_exercise(
    session: Session,
    *,
    name: str,
    muscle_group: MuscleGroup,
    equipment: Equipment,
    created_by_user_id: int | None = None,
    description: str | None = None,
    category: ExerciseCategory | None = None,
    icon: str | None = None,
    image_url: str | None = None,
    video_url: str | None = None,
) -> Exercise:
    exercise = Exercise(
        name=name,
        muscle_group=muscle_group,
        equipment=equipment,
        created_by_user_id=created_by_user_id,
        description=description,
        category=category,
        icon=icon,
        image_url=image_url,
        video_url=video_url,
    )
    session.add(exercise)
    session.commit()
    session.refresh(exercise)
    return exercise

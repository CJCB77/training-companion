from sqlalchemy import or_
from sqlmodel import Session, select

from app.models.enums import Equipment, ExerciseCategory, MuscleGroup
from app.models.exercise import Exercise


def list_exercises(
    session: Session,
    user_id: int,
    muscle_group: MuscleGroup | None = None,
) -> list[Exercise]:
    """System exercises plus the caller's own custom ones, ordered by name.

    A user never sees another user's custom exercises.
    """
    statement = select(Exercise).where(
        or_(
            Exercise.created_by_user_id.is_(None),  # type: ignore[union-attr]
            Exercise.created_by_user_id == user_id,
        )
    )
    if muscle_group is not None:
        statement = statement.where(Exercise.muscle_group == muscle_group)
    statement = statement.order_by(Exercise.name)
    return list(session.exec(statement).all())


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

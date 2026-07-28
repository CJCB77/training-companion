from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.enums import ExerciseCategory, MuscleGroup
from app.models.profile import Profile
from app.schemas.exercises import ExerciseCreate, ExerciseRead
from app.services import exercises as exercises_service

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get("", response_model=list[ExerciseRead])
def list_exercises(
    search: str | None = None,
    muscle_group: MuscleGroup | None = None,
    category: ExerciseCategory | None = None,
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ExerciseRead]:
    return exercises_service.list_exercises(
        session,
        user_id=current_user.id,
        search=search,
        muscle_group=muscle_group,
        category=category,
    )


@router.post("", response_model=ExerciseRead, status_code=status.HTTP_201_CREATED)
def create_exercise(
    payload: ExerciseCreate,
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ExerciseRead:
    try:
        return exercises_service.create_custom_exercise(
            session, user_id=current_user.id, payload=payload
        )
    except exercises_service.DuplicateExerciseNameError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An exercise with that name already exists",
        ) from exc

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.profile import Profile
from app.schemas.workout_sessions import (
    WorkoutSessionCreate,
    WorkoutSessionRead,
    WorkoutSessionUpdate,
)
from app.services import training_weeks as training_weeks_service
from app.services import workout_sessions as workout_sessions_service

# No prefix: routes span two path roots (/training-weeks/{id}/workout-sessions
# and /workout-sessions/{id}), so each path is written out in full on its
# decorator.
router = APIRouter(tags=["workout-sessions"])


def _session_not_found() -> HTTPException:
    # Access-denied maps here too, deliberately: a non-owner shouldn't be able to
    # distinguish "not yours" from "doesn't exist".
    return HTTPException(status.HTTP_404_NOT_FOUND, "Workout session not found")


def _week_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Training week not found")


def _invalid_update(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


@router.post(
    "/training-weeks/{week_id}/workout-sessions",
    response_model=WorkoutSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workout_session(
    week_id: int,
    payload: WorkoutSessionCreate,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> WorkoutSessionRead:
    try:
        return workout_sessions_service.create_workout_session_for_week(
            db_session, user_id=current_user.id, week_id=week_id, payload=payload
        )
    except (
        training_weeks_service.TrainingWeekNotFoundError,
        training_weeks_service.TrainingWeekAccessDeniedError,
    ) as exc:
        raise _week_not_found() from exc


@router.get(
    "/training-weeks/{week_id}/workout-sessions",
    response_model=list[WorkoutSessionRead],
)
def list_workout_sessions(
    week_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> list[WorkoutSessionRead]:
    try:
        return workout_sessions_service.list_workout_sessions(
            db_session, user_id=current_user.id, week_id=week_id
        )
    except (
        training_weeks_service.TrainingWeekNotFoundError,
        training_weeks_service.TrainingWeekAccessDeniedError,
    ) as exc:
        raise _week_not_found() from exc


@router.get("/workout-sessions/{session_id}", response_model=WorkoutSessionRead)
def get_workout_session(
    session_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> WorkoutSessionRead:
    try:
        return workout_sessions_service.get_owned_workout_session(
            db_session, user_id=current_user.id, workout_session_id=session_id
        )
    except (
        workout_sessions_service.WorkoutSessionNotFoundError,
        workout_sessions_service.WorkoutSessionAccessDeniedError,
    ) as exc:
        raise _session_not_found() from exc


@router.put("/workout-sessions/{session_id}", response_model=WorkoutSessionRead)
def update_workout_session(
    session_id: int,
    payload: WorkoutSessionUpdate,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> WorkoutSessionRead:
    try:
        return workout_sessions_service.update_workout_session(
            db_session,
            user_id=current_user.id,
            workout_session_id=session_id,
            payload=payload,
        )
    except (
        workout_sessions_service.WorkoutSessionNotFoundError,
        workout_sessions_service.WorkoutSessionAccessDeniedError,
    ) as exc:
        raise _session_not_found() from exc
    except workout_sessions_service.InvalidWorkoutSessionUpdateError as exc:
        raise _invalid_update(str(exc)) from exc


@router.delete("/workout-sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout_session(
    session_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> None:
    try:
        workout_sessions_service.delete_workout_session(
            db_session, user_id=current_user.id, workout_session_id=session_id
        )
    except (
        workout_sessions_service.WorkoutSessionNotFoundError,
        workout_sessions_service.WorkoutSessionAccessDeniedError,
    ) as exc:
        raise _session_not_found() from exc

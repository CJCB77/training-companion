from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.profile import Profile
from app.schemas.exercise_performances import (
    ExercisePerformanceCreate,
    ExercisePerformanceRead,
    ExercisePerformanceUpdate,
)
from app.services import exercise_performances as exercise_performances_service
from app.services import exercise_prescriptions as exercise_prescriptions_service
from app.services import workout_sessions as workout_sessions_service

# No prefix: routes span three path roots (/exercise-prescriptions/{id}/
# performances, /workout-sessions/{id}/performances, and /exercise-
# performances/{id}), so each path is written out in full on its decorator.
router = APIRouter(tags=["exercise-performances"])


def _performance_not_found() -> HTTPException:
    # Access-denied maps here too, deliberately: a non-owner shouldn't be able to
    # distinguish "not yours" from "doesn't exist".
    return HTTPException(status.HTTP_404_NOT_FOUND, "Exercise performance not found")


def _prescription_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Exercise prescription not found")


def _session_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Workout session not found")


def _invalid_update(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


@router.post(
    "/exercise-prescriptions/{prescription_id}/performances",
    response_model=ExercisePerformanceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_exercise_performance(
    prescription_id: int,
    payload: ExercisePerformanceCreate,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> ExercisePerformanceRead:
    try:
        return (
            exercise_performances_service.create_exercise_performance_for_prescription(
                db_session,
                user_id=current_user.id,
                prescription_id=prescription_id,
                payload=payload,
            )
        )
    except (
        exercise_prescriptions_service.ExercisePrescriptionNotFoundError,
        exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError,
    ) as exc:
        raise _prescription_not_found() from exc


@router.get(
    "/exercise-prescriptions/{prescription_id}/performances",
    response_model=list[ExercisePerformanceRead],
)
def list_performances_for_prescription(
    prescription_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> list[ExercisePerformanceRead]:
    try:
        return exercise_performances_service.list_performances_for_prescription(
            db_session, user_id=current_user.id, prescription_id=prescription_id
        )
    except (
        exercise_prescriptions_service.ExercisePrescriptionNotFoundError,
        exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError,
    ) as exc:
        raise _prescription_not_found() from exc


@router.get(
    "/workout-sessions/{session_id}/performances",
    response_model=list[ExercisePerformanceRead],
)
def list_performances_for_session(
    session_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> list[ExercisePerformanceRead]:
    try:
        return exercise_performances_service.list_performances_for_session(
            db_session, user_id=current_user.id, workout_session_id=session_id
        )
    except (
        workout_sessions_service.WorkoutSessionNotFoundError,
        workout_sessions_service.WorkoutSessionAccessDeniedError,
    ) as exc:
        raise _session_not_found() from exc


@router.get(
    "/exercise-performances/{performance_id}",
    response_model=ExercisePerformanceRead,
)
def get_exercise_performance(
    performance_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> ExercisePerformanceRead:
    try:
        return exercise_performances_service.get_owned_exercise_performance(
            db_session, user_id=current_user.id, performance_id=performance_id
        )
    except (
        exercise_performances_service.ExercisePerformanceNotFoundError,
        exercise_performances_service.ExercisePerformanceAccessDeniedError,
    ) as exc:
        raise _performance_not_found() from exc


@router.put(
    "/exercise-performances/{performance_id}",
    response_model=ExercisePerformanceRead,
)
def update_exercise_performance(
    performance_id: int,
    payload: ExercisePerformanceUpdate,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> ExercisePerformanceRead:
    try:
        return exercise_performances_service.update_exercise_performance(
            db_session,
            user_id=current_user.id,
            performance_id=performance_id,
            payload=payload,
        )
    except (
        exercise_performances_service.ExercisePerformanceNotFoundError,
        exercise_performances_service.ExercisePerformanceAccessDeniedError,
    ) as exc:
        raise _performance_not_found() from exc
    except exercise_performances_service.InvalidExercisePerformanceUpdateError as exc:
        raise _invalid_update(str(exc)) from exc


@router.delete(
    "/exercise-performances/{performance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_exercise_performance(
    performance_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> None:
    try:
        exercise_performances_service.delete_exercise_performance(
            db_session, user_id=current_user.id, performance_id=performance_id
        )
    except (
        exercise_performances_service.ExercisePerformanceNotFoundError,
        exercise_performances_service.ExercisePerformanceAccessDeniedError,
    ) as exc:
        raise _performance_not_found() from exc

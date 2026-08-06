from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.profile import Profile
from app.schemas.exercise_prescriptions import (
    ExercisePrescriptionCreate,
    ExercisePrescriptionRead,
    ExercisePrescriptionUpdate,
)
from app.services import exercise_prescriptions as exercise_prescriptions_service
from app.services import workout_sessions as workout_sessions_service

# No prefix: routes span two path roots (/workout-sessions/{id}/exercise-
# prescriptions and /exercise-prescriptions/{id}), so each path is written out
# in full on its decorator.
router = APIRouter(tags=["exercise-prescriptions"])


def _prescription_not_found() -> HTTPException:
    # Access-denied maps here too, deliberately: a non-owner shouldn't be able to
    # distinguish "not yours" from "doesn't exist".
    return HTTPException(status.HTTP_404_NOT_FOUND, "Exercise prescription not found")


def _session_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Workout session not found")


def _exercise_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found")


def _invalid_update(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


@router.post(
    "/workout-sessions/{session_id}/exercise-prescriptions",
    response_model=ExercisePrescriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_exercise_prescription(
    session_id: int,
    payload: ExercisePrescriptionCreate,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> ExercisePrescriptionRead:
    try:
        return exercise_prescriptions_service.create_exercise_prescription_for_session(
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
    except exercise_prescriptions_service.ExerciseNotVisibleError as exc:
        raise _exercise_not_found() from exc


@router.get(
    "/workout-sessions/{session_id}/exercise-prescriptions",
    response_model=list[ExercisePrescriptionRead],
)
def list_exercise_prescriptions(
    session_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> list[ExercisePrescriptionRead]:
    try:
        return exercise_prescriptions_service.list_exercise_prescriptions(
            db_session, user_id=current_user.id, workout_session_id=session_id
        )
    except (
        workout_sessions_service.WorkoutSessionNotFoundError,
        workout_sessions_service.WorkoutSessionAccessDeniedError,
    ) as exc:
        raise _session_not_found() from exc


@router.get(
    "/exercise-prescriptions/{prescription_id}",
    response_model=ExercisePrescriptionRead,
)
def get_exercise_prescription(
    prescription_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> ExercisePrescriptionRead:
    try:
        return exercise_prescriptions_service.get_owned_exercise_prescription(
            db_session, user_id=current_user.id, prescription_id=prescription_id
        )
    except (
        exercise_prescriptions_service.ExercisePrescriptionNotFoundError,
        exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError,
    ) as exc:
        raise _prescription_not_found() from exc


@router.put(
    "/exercise-prescriptions/{prescription_id}",
    response_model=ExercisePrescriptionRead,
)
def update_exercise_prescription(
    prescription_id: int,
    payload: ExercisePrescriptionUpdate,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> ExercisePrescriptionRead:
    try:
        return exercise_prescriptions_service.update_exercise_prescription(
            db_session,
            user_id=current_user.id,
            prescription_id=prescription_id,
            payload=payload,
        )
    except (
        exercise_prescriptions_service.ExercisePrescriptionNotFoundError,
        exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError,
    ) as exc:
        raise _prescription_not_found() from exc
    except exercise_prescriptions_service.ExerciseNotVisibleError as exc:
        raise _exercise_not_found() from exc
    except exercise_prescriptions_service.InvalidExercisePrescriptionUpdateError as exc:
        raise _invalid_update(str(exc)) from exc


@router.delete(
    "/exercise-prescriptions/{prescription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_exercise_prescription(
    prescription_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> None:
    try:
        exercise_prescriptions_service.delete_exercise_prescription(
            db_session, user_id=current_user.id, prescription_id=prescription_id
        )
    except (
        exercise_prescriptions_service.ExercisePrescriptionNotFoundError,
        exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError,
    ) as exc:
        raise _prescription_not_found() from exc

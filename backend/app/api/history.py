from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.profile import Profile
from app.schemas.history import (
    CompletedSessionRead,
    OneRmTrendPointRead,
    PersonalRecordRead,
)
from app.services import history as history_service

router = APIRouter(prefix="/history", tags=["history"])


def _program_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Program not found")


def _session_not_found() -> HTTPException:
    # Access-denied maps here too, deliberately: a non-owner shouldn't be able
    # to distinguish "not yours" from "doesn't exist".
    return HTTPException(status.HTTP_404_NOT_FOUND, "Workout session not found")


def _exercise_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not found")


@router.get("/sessions", response_model=list[CompletedSessionRead])
def list_completed_sessions(
    program_id: int | None = None,
    limit: int = Query(
        default=history_service.DEFAULT_LIST_LIMIT,
        ge=1,
        le=history_service.MAX_LIST_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> list[CompletedSessionRead]:
    try:
        return history_service.list_completed_sessions(
            db_session,
            user_id=current_user.id,
            program_id=program_id,
            limit=limit,
            offset=offset,
        )
    except (
        history_service.ProgramNotFoundError,
        history_service.ProgramAccessDeniedError,
    ) as exc:
        raise _program_not_found() from exc


@router.get("/personal-records", response_model=list[PersonalRecordRead])
def get_personal_records(
    exercise_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> list[PersonalRecordRead]:
    try:
        return history_service.get_personal_records(
            db_session,
            user_id=current_user.id,
            exercise_id=exercise_id,
            display_unit=current_user.default_weight_unit,
        )
    except history_service.ExerciseNotFoundError as exc:
        raise _exercise_not_found() from exc


@router.get(
    "/sessions/{session_id}/personal-records",
    response_model=list[PersonalRecordRead],
)
def get_session_personal_records(
    session_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> list[PersonalRecordRead]:
    try:
        return history_service.get_session_personal_records(
            db_session,
            user_id=current_user.id,
            workout_session_id=session_id,
            display_unit=current_user.default_weight_unit,
        )
    except (
        history_service.WorkoutSessionNotFoundError,
        history_service.WorkoutSessionAccessDeniedError,
    ) as exc:
        raise _session_not_found() from exc


@router.get(
    "/exercises/{exercise_id}/one-rm-trend",
    response_model=list[OneRmTrendPointRead],
)
def get_one_rm_trend(
    exercise_id: int,
    program_id: int | None = None,
    limit: int = Query(
        default=history_service.DEFAULT_LIST_LIMIT,
        ge=1,
        le=history_service.MAX_LIST_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> list[OneRmTrendPointRead]:
    try:
        return history_service.get_one_rm_trend(
            db_session,
            user_id=current_user.id,
            exercise_id=exercise_id,
            program_id=program_id,
            limit=limit,
            offset=offset,
            display_unit=current_user.default_weight_unit,
        )
    except history_service.ExerciseNotFoundError as exc:
        raise _exercise_not_found() from exc
    except (
        history_service.ProgramNotFoundError,
        history_service.ProgramAccessDeniedError,
    ) as exc:
        raise _program_not_found() from exc

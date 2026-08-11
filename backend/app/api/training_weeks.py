from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.profile import Profile
from app.schemas.training_weeks import (
    TrainingWeekCreate,
    TrainingWeekGenerateRequest,
    TrainingWeekRead,
    TrainingWeekUpdate,
)
from app.services import programs as programs_service
from app.services import training_weeks as training_weeks_service

# No prefix: routes span two path roots (/programs/{id}/training-weeks and
# /training-weeks/{id}), so each path is written out in full on its decorator.
router = APIRouter(tags=["training-weeks"])


def _week_not_found() -> HTTPException:
    # Access-denied maps here too, deliberately: a non-owner shouldn't be able to
    # distinguish "not yours" from "doesn't exist".
    return HTTPException(status.HTTP_404_NOT_FOUND, "Training week not found")


def _program_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Program not found")


def _duplicate_week_number() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT, "That week number is already used in this program"
    )


def _invalid_update(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


@router.post(
    "/programs/{program_id}/training-weeks",
    response_model=TrainingWeekRead,
    status_code=status.HTTP_201_CREATED,
)
def create_training_week(
    program_id: int,
    payload: TrainingWeekCreate,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> TrainingWeekRead:
    try:
        return training_weeks_service.create_training_week_for_program(
            db_session, user_id=current_user.id, program_id=program_id, payload=payload
        )
    except (
        programs_service.ProgramNotFoundError,
        programs_service.ProgramAccessDeniedError,
    ) as exc:
        raise _program_not_found() from exc
    except training_weeks_service.DuplicateWeekNumberError as exc:
        raise _duplicate_week_number() from exc


@router.get(
    "/programs/{program_id}/training-weeks", response_model=list[TrainingWeekRead]
)
def list_training_weeks(
    program_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> list[TrainingWeekRead]:
    try:
        return training_weeks_service.list_training_weeks(
            db_session, user_id=current_user.id, program_id=program_id
        )
    except (
        programs_service.ProgramNotFoundError,
        programs_service.ProgramAccessDeniedError,
    ) as exc:
        raise _program_not_found() from exc


@router.get("/training-weeks/{week_id}", response_model=TrainingWeekRead)
def get_training_week(
    week_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> TrainingWeekRead:
    try:
        return training_weeks_service.get_owned_training_week(
            db_session, user_id=current_user.id, week_id=week_id
        )
    except (
        training_weeks_service.TrainingWeekNotFoundError,
        training_weeks_service.TrainingWeekAccessDeniedError,
    ) as exc:
        raise _week_not_found() from exc


@router.put("/training-weeks/{week_id}", response_model=TrainingWeekRead)
def update_training_week(
    week_id: int,
    payload: TrainingWeekUpdate,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> TrainingWeekRead:
    try:
        return training_weeks_service.update_training_week(
            db_session, user_id=current_user.id, week_id=week_id, payload=payload
        )
    except (
        training_weeks_service.TrainingWeekNotFoundError,
        training_weeks_service.TrainingWeekAccessDeniedError,
    ) as exc:
        raise _week_not_found() from exc
    except training_weeks_service.DuplicateWeekNumberError as exc:
        raise _duplicate_week_number() from exc
    except training_weeks_service.InvalidTrainingWeekUpdateError as exc:
        raise _invalid_update(str(exc)) from exc


@router.post(
    "/training-weeks/{week_id}/generate-next",
    response_model=TrainingWeekRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_next_training_week(
    week_id: int,
    payload: TrainingWeekGenerateRequest = TrainingWeekGenerateRequest(),
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> TrainingWeekRead:
    try:
        return training_weeks_service.generate_next_training_week(
            db_session, user_id=current_user.id, week_id=week_id, payload=payload
        )
    except (
        training_weeks_service.TrainingWeekNotFoundError,
        training_weeks_service.TrainingWeekAccessDeniedError,
    ) as exc:
        raise _week_not_found() from exc
    except training_weeks_service.DuplicateWeekNumberError as exc:
        raise _duplicate_week_number() from exc


@router.delete("/training-weeks/{week_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_training_week(
    week_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> None:
    try:
        training_weeks_service.delete_training_week(
            db_session, user_id=current_user.id, week_id=week_id
        )
    except (
        training_weeks_service.TrainingWeekNotFoundError,
        training_weeks_service.TrainingWeekAccessDeniedError,
    ) as exc:
        raise _week_not_found() from exc

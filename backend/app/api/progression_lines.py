from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.profile import Profile
from app.schemas.progression_lines import ProgressionLineRead, ProgressionLineUpdate
from app.services import programs as programs_service
from app.services import progression_lines as progression_lines_service

# No prefix: routes span two path roots (/programs/{id}/exercises/{exercise_id}/
# progression-lines and /progression-lines/{id}), matching
# app/api/exercise_prescriptions.py's pattern.
router = APIRouter(tags=["progression-lines"])


def _program_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Program not found")


def _line_not_found() -> HTTPException:
    # Access-denied maps here too, deliberately: a non-owner shouldn't be able to
    # distinguish "not yours" from "doesn't exist".
    return HTTPException(status.HTTP_404_NOT_FOUND, "Progression line not found")


@router.get(
    "/programs/{program_id}/exercises/{exercise_id}/progression-lines",
    response_model=list[ProgressionLineRead],
)
def list_progression_lines(
    program_id: int,
    exercise_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> list[ProgressionLineRead]:
    try:
        return progression_lines_service.list_progression_lines(
            db_session,
            user_id=current_user.id,
            program_id=program_id,
            exercise_id=exercise_id,
        )
    except (
        programs_service.ProgramNotFoundError,
        programs_service.ProgramAccessDeniedError,
    ) as exc:
        raise _program_not_found() from exc


@router.patch(
    "/progression-lines/{line_id}",
    response_model=ProgressionLineRead,
)
def rename_progression_line(
    line_id: int,
    payload: ProgressionLineUpdate,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> ProgressionLineRead:
    try:
        return progression_lines_service.rename_progression_line(
            db_session, user_id=current_user.id, line_id=line_id, payload=payload
        )
    except (
        progression_lines_service.ProgressionLineNotFoundError,
        progression_lines_service.ProgressionLineAccessDeniedError,
    ) as exc:
        raise _line_not_found() from exc

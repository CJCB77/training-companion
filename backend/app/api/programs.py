from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.profile import Profile
from app.schemas.programs import (
    ProgramCreate,
    ProgramDuplicateRequest,
    ProgramRead,
    ProgramUpdate,
)
from app.services import programs as programs_service

router = APIRouter(prefix="/programs", tags=["programs"])


def _not_found() -> HTTPException:
    # Access-denied maps here too, deliberately: a non-owner shouldn't be able to
    # distinguish "not yours" from "doesn't exist".
    return HTTPException(status.HTTP_404_NOT_FOUND, "Program not found")


@router.post("", response_model=ProgramRead, status_code=status.HTTP_201_CREATED)
def create_program(
    payload: ProgramCreate,
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProgramRead:
    return programs_service.create_program_for_user(
        session, user_id=current_user.id, payload=payload
    )


@router.get("", response_model=list[ProgramRead])
def list_programs(
    include_archived: bool = False,
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ProgramRead]:
    return programs_service.list_programs(
        session, user_id=current_user.id, include_archived=include_archived
    )


@router.get("/{program_id}", response_model=ProgramRead)
def get_program(
    program_id: int,
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProgramRead:
    try:
        return programs_service.get_owned_program(
            session, user_id=current_user.id, program_id=program_id
        )
    except (
        programs_service.ProgramNotFoundError,
        programs_service.ProgramAccessDeniedError,
    ) as exc:
        raise _not_found() from exc


@router.put("/{program_id}", response_model=ProgramRead)
def update_program(
    program_id: int,
    payload: ProgramUpdate,
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProgramRead:
    try:
        return programs_service.update_program(
            session,
            user_id=current_user.id,
            program_id=program_id,
            payload=payload,
        )
    except (
        programs_service.ProgramNotFoundError,
        programs_service.ProgramAccessDeniedError,
    ) as exc:
        raise _not_found() from exc


@router.post("/{program_id}/archive", response_model=ProgramRead)
def archive_program(
    program_id: int,
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProgramRead:
    try:
        return programs_service.archive_program(
            session, user_id=current_user.id, program_id=program_id
        )
    except (
        programs_service.ProgramNotFoundError,
        programs_service.ProgramAccessDeniedError,
    ) as exc:
        raise _not_found() from exc


@router.post("/{program_id}/unarchive", response_model=ProgramRead)
def unarchive_program(
    program_id: int,
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProgramRead:
    try:
        return programs_service.unarchive_program(
            session, user_id=current_user.id, program_id=program_id
        )
    except (
        programs_service.ProgramNotFoundError,
        programs_service.ProgramAccessDeniedError,
    ) as exc:
        raise _not_found() from exc


@router.post(
    "/{program_id}/duplicate",
    response_model=ProgramRead,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_program(
    program_id: int,
    payload: ProgramDuplicateRequest = ProgramDuplicateRequest(),
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProgramRead:
    try:
        return programs_service.duplicate_program(
            session,
            user_id=current_user.id,
            program_id=program_id,
            payload=payload,
        )
    except (
        programs_service.ProgramNotFoundError,
        programs_service.ProgramAccessDeniedError,
    ) as exc:
        raise _not_found() from exc


@router.delete("/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_program(
    program_id: int,
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    try:
        programs_service.delete_program(
            session, user_id=current_user.id, program_id=program_id
        )
    except (
        programs_service.ProgramNotFoundError,
        programs_service.ProgramAccessDeniedError,
    ) as exc:
        raise _not_found() from exc

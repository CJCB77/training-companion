from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.profile import Profile
from app.schemas.program_templates import (
    ProgramGenerateRequest,
    ProgramTemplateDetail,
    ProgramTemplateRead,
)
from app.schemas.programs import ProgramRead
from app.services import program_templates as program_templates_service

router = APIRouter(prefix="/program-templates", tags=["program-templates"])


def _template_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Program template not found")


@router.get("", response_model=list[ProgramTemplateRead])
def list_program_templates(
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ProgramTemplateRead]:
    return program_templates_service.list_templates(session)


@router.get("/{template_id}", response_model=ProgramTemplateDetail)
def get_program_template(
    template_id: int,
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProgramTemplateDetail:
    try:
        return program_templates_service.get_template(session, template_id)
    except program_templates_service.ProgramTemplateNotFoundError as exc:
        raise _template_not_found() from exc


@router.post(
    "/{template_id}/generate",
    response_model=ProgramRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_program_from_template(
    template_id: int,
    payload: ProgramGenerateRequest = ProgramGenerateRequest(),
    current_user: Profile = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ProgramRead:
    try:
        return program_templates_service.generate_program_from_template(
            session,
            user_id=current_user.id,
            template_id=template_id,
            payload=payload,
        )
    except program_templates_service.ProgramTemplateNotFoundError as exc:
        raise _template_not_found() from exc

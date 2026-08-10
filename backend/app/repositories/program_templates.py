from sqlmodel import Session, select

from app.models.program_template import ProgramTemplate


def list_program_templates(session: Session) -> list[ProgramTemplate]:
    return list(
        session.exec(select(ProgramTemplate).order_by(ProgramTemplate.name)).all()
    )


def get_program_template(
    session: Session, template_id: int
) -> ProgramTemplate | None:
    return session.get(ProgramTemplate, template_id)

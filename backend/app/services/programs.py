"""Program CRUD business logic: ownership enforcement lives here, not in the routes.

Routes only translate these exceptions into HTTP responses.
"""

from sqlmodel import Session

from app.models.program import Program
from app.repositories import programs as programs_repo
from app.schemas.programs import ProgramCreate, ProgramUpdate


class ProgramNotFoundError(Exception):
    """No program exists with that id (or it's been soft-deleted)."""


class ProgramAccessDeniedError(Exception):
    """The program exists but belongs to a different user."""


def create_program_for_user(
    session: Session, *, user_id: int, payload: ProgramCreate
) -> Program:
    # Enforce a single active program per user: if this one comes in active, turn
    # off any others first, in the same transaction create_program commits.
    if payload.is_active:
        programs_repo.deactivate_other_active_programs(session, user_id)
    return programs_repo.create_program(
        session,
        user_id=user_id,
        name=payload.name,
        weight_unit=payload.weight_unit,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_active=payload.is_active,
        default_progression_type=payload.default_progression_type,
        default_progression_params=payload.default_progression_params,
    )


def list_programs(session: Session, *, user_id: int) -> list[Program]:
    return programs_repo.list_programs_for_user(session, user_id=user_id)


def get_owned_program(session: Session, *, user_id: int, program_id: int) -> Program:
    """Fetch a program the caller owns, or raise.

    Not-found and access-denied are kept as distinct exceptions for callers that care,
    but the API layer maps both to 404 so a non-owner can't learn a program id exists.
    """
    program = programs_repo.get_program(session, program_id)
    if program is None:
        raise ProgramNotFoundError(program_id)
    if program.user_id != user_id:
        raise ProgramAccessDeniedError(program_id)
    return program


def update_program(
    session: Session, *, user_id: int, program_id: int, payload: ProgramUpdate
) -> Program:
    program = get_owned_program(session, user_id=user_id, program_id=program_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return program
    # Same single-active enforcement as create: activating this program deactivates
    # any other active one owned by the same user, atomically with this update.
    if updates.get("is_active") is True:
        programs_repo.deactivate_other_active_programs(
            session, user_id, exclude_program_id=program.id
        )
    return programs_repo.update_program(session, program, **updates)


def delete_program(session: Session, *, user_id: int, program_id: int) -> None:
    program = get_owned_program(session, user_id=user_id, program_id=program_id)
    programs_repo.soft_delete_program(session, program)

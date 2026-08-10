"""Program CRUD business logic: ownership enforcement lives here, not in the routes.

Routes only translate these exceptions into HTTP responses.
"""

from sqlmodel import Session

from app.models.program import Program
from app.repositories import programs as programs_repo
from app.schemas.programs import ProgramCreate, ProgramDuplicateRequest, ProgramUpdate


class ProgramNotFoundError(Exception):
    """No program exists with that id."""


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
        # SQLModel won't serialize a ProgressionParams instance into the JSONB
        # column — dump it to a plain dict first.
        default_progression_params=(
            payload.default_progression_params.model_dump(exclude_unset=True)
            if payload.default_progression_params is not None
            else None
        ),
    )


def list_programs(
    session: Session, *, user_id: int, include_archived: bool = False
) -> list[Program]:
    return programs_repo.list_programs_for_user(
        session, user_id=user_id, include_archived=include_archived
    )


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
    if updates.get("is_active") is True:
        # Activating an archived program implicitly unarchives it first — an archived
        # program is never active. A separate commit here is fine: the intermediate
        # state (unarchived, not yet active) still satisfies that invariant, so a
        # partial failure between the two commits leaves valid data.
        if program.archived_at is not None:
            program = programs_repo.unarchive_program(session, program)
        # Same single-active enforcement as create: activating this program deactivates
        # any other active one owned by the same user, atomically with this update.
        programs_repo.deactivate_other_active_programs(
            session, user_id, exclude_program_id=program.id
        )
    return programs_repo.update_program(session, program, **updates)


def archive_program(session: Session, *, user_id: int, program_id: int) -> Program:
    program = get_owned_program(session, user_id=user_id, program_id=program_id)
    return programs_repo.archive_program(session, program)


def unarchive_program(session: Session, *, user_id: int, program_id: int) -> Program:
    program = get_owned_program(session, user_id=user_id, program_id=program_id)
    return programs_repo.unarchive_program(session, program)


def delete_program(session: Session, *, user_id: int, program_id: int) -> None:
    program = get_owned_program(session, user_id=user_id, program_id=program_id)
    programs_repo.delete_program(session, program)


def duplicate_program(
    session: Session,
    *,
    user_id: int,
    program_id: int,
    payload: ProgramDuplicateRequest,
) -> Program:
    """Deep-copy a program the caller owns into a new, independent one.

    Deliberately does not call deactivate_other_active_programs: the copy is always
    created inactive, so TRAIN-10's single-active invariant holds by construction
    rather than by mutating the user's other programs.
    """
    source = get_owned_program(session, user_id=user_id, program_id=program_id)
    name = payload.name or f"{source.name} (Copy)"
    return programs_repo.duplicate_program_tree(session, source=source, name=name)

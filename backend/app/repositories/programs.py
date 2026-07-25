from datetime import date, datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models.enums import ProgressionType, WeightUnit
from app.models.program import Program


def create_program(
    session: Session,
    *,
    user_id: int,
    name: str,
    weight_unit: WeightUnit,
    description: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    is_active: bool = False,
    default_progression_type: ProgressionType | None = None,
    default_progression_params: dict | None = None,
) -> Program:
    program = Program(
        user_id=user_id,
        name=name,
        weight_unit=weight_unit,
        description=description,
        start_date=start_date,
        end_date=end_date,
        is_active=is_active,
        default_progression_type=default_progression_type,
        default_progression_params=default_progression_params,
    )
    session.add(program)
    session.commit()
    session.refresh(program)
    return program


def get_program(session: Session, program_id: int) -> Program | None:
    # No archived filter here: a fetch by id must return the program regardless of
    # archived state, or unarchive (and any "view an archived program" flow) would be
    # unreachable. Archiving only affects list_programs_for_user's default view.
    return session.get(Program, program_id)


def list_programs_for_user(
    session: Session, user_id: int, *, include_archived: bool = False
) -> list[Program]:
    statement = select(Program).where(Program.user_id == user_id)
    if not include_archived:
        statement = statement.where(Program.archived_at.is_(None))  # type: ignore[union-attr]
    return list(
        session.exec(
            statement.order_by(Program.created_at.desc())  # type: ignore[union-attr]
        ).all()
    )


def get_active_program(session: Session, user_id: int) -> Program | None:
    # No archived_at filter: under the archive/active invariant (archiving a program
    # clears is_active, and activating a program unarchives it first), an archived
    # program can never be active, so is_active alone is sufficient here.
    return session.exec(
        select(Program).where(
            Program.user_id == user_id,
            Program.is_active.is_(True),  # type: ignore[union-attr]
        )
    ).first()


def deactivate_other_active_programs(
    session: Session, user_id: int, *, exclude_program_id: int | None = None
) -> None:
    """Turn off `is_active` on every other active program owned by this user.

    Does not commit — the caller (creating or activating a program) adds this to the
    same session and commits once, so the deactivation and the activation land in a
    single transaction. Without this, get_active_program's unordered `.first()` would
    have no way to pick a single "current" program once more than one is active.

    No archived_at filter: an archived program is never active (see get_active_program),
    so filtering on it here would only mask a violated invariant rather than surface it —
    worst case, leaving a second program active.
    """
    statement = select(Program).where(
        Program.user_id == user_id,
        Program.is_active.is_(True),  # type: ignore[union-attr]
    )
    if exclude_program_id is not None:
        statement = statement.where(Program.id != exclude_program_id)
    for other in session.exec(statement).all():
        other.is_active = False
        session.add(other)


# Fields callers are allowed to change via update_program. An explicit allow-list
# instead of trusting **fields keeps this from becoming a mass-assignment sink for
# columns like user_id/id/archived_at that must only change through their own,
# purpose-built paths (archive_program/unarchive_program, ownership is fixed at
# creation).
_UPDATABLE_FIELDS = {
    "name",
    "description",
    "start_date",
    "end_date",
    "is_active",
    "weight_unit",
    "default_progression_type",
    "default_progression_params",
}


def update_program(session: Session, program: Program, **fields: Any) -> Program:
    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"update_program cannot set fields: {sorted(unknown)}")
    for key, value in fields.items():
        setattr(program, key, value)
    session.add(program)
    session.commit()
    session.refresh(program)
    return program


def archive_program(session: Session, program: Program) -> Program:
    """Hide a program from the default list without touching the week/session/
    prescription tree beneath it, and clear is_active (an archived program is never
    active). Idempotent: if already archived, the existing archived_at timestamp is
    left alone so "when was this archived" stays stable.
    """
    if program.archived_at is None:
        program.archived_at = datetime.now(timezone.utc)
    program.is_active = False
    session.add(program)
    session.commit()
    session.refresh(program)
    return program


def unarchive_program(session: Session, program: Program) -> Program:
    """Restore a program to the default list. Idempotent on a non-archived program.
    Does not touch is_active — activating happens separately, through update_program.
    """
    program.archived_at = None
    session.add(program)
    session.commit()
    session.refresh(program)
    return program


def delete_program(session: Session, program: Program) -> None:
    """Permanently remove a program and its owned tree (TrainingWeek/WorkoutSession/
    ExercisePrescription cascade via the ORM/DB relationships already configured on
    Program.training_weeks and their FKs). Exercise rows are never touched: prescriptions
    reference Exercise with ondelete="RESTRICT" and no cascading relationship toward it.
    """
    session.delete(program)
    session.commit()

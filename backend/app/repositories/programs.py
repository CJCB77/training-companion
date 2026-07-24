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


def get_program(
    session: Session, program_id: int, *, include_deleted: bool = False
) -> Program | None:
    program = session.get(Program, program_id)
    if program is not None and program.deleted_at is not None and not include_deleted:
        return None
    return program


def list_programs_for_user(session: Session, user_id: int) -> list[Program]:
    return list(
        session.exec(
            select(Program)
            .where(
                Program.user_id == user_id,
                Program.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .order_by(Program.created_at.desc())  # type: ignore[union-attr]
        ).all()
    )


def get_active_program(session: Session, user_id: int) -> Program | None:
    return session.exec(
        select(Program).where(
            Program.user_id == user_id,
            Program.is_active.is_(True),  # type: ignore[union-attr]
            Program.deleted_at.is_(None),  # type: ignore[union-attr]
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
    """
    statement = select(Program).where(
        Program.user_id == user_id,
        Program.is_active.is_(True),  # type: ignore[union-attr]
        Program.deleted_at.is_(None),  # type: ignore[union-attr]
    )
    if exclude_program_id is not None:
        statement = statement.where(Program.id != exclude_program_id)
    for other in session.exec(statement).all():
        other.is_active = False
        session.add(other)


# Fields callers are allowed to change via update_program. An explicit allow-list
# instead of trusting **fields keeps this from becoming a mass-assignment sink for
# columns like user_id/id/deleted_at that must only change through their own,
# purpose-built paths (soft_delete_program, ownership is fixed at creation).
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


def soft_delete_program(session: Session, program: Program) -> None:
    """Mark a program deleted without touching the week/session/prescription tree
    beneath it. Repositories/services above filter it out of get/list going forward.
    """
    program.deleted_at = datetime.now(timezone.utc)
    session.add(program)
    session.commit()

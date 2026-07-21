from datetime import date

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
    return session.get(Program, program_id)


def list_programs_for_user(session: Session, user_id: int) -> list[Program]:
    return list(
        session.exec(
            select(Program)
            .where(Program.user_id == user_id)
            .order_by(Program.created_at.desc())  # type: ignore[union-attr]
        ).all()
    )


def get_active_program(session: Session, user_id: int) -> Program | None:
    return session.exec(
        select(Program).where(
            Program.user_id == user_id,
            Program.is_active.is_(True),  # type: ignore[union-attr]
        )
    ).first()

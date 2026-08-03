from typing import Any

from sqlmodel import Session, select

from app.models.program import Program
from app.models.training_week import TrainingWeek


def create_training_week(
    session: Session,
    *,
    program_id: int,
    week_number: int,
    name: str | None = None,
) -> TrainingWeek:
    week = TrainingWeek(program_id=program_id, week_number=week_number, name=name)
    session.add(week)
    session.commit()
    session.refresh(week)
    return week


def get_training_week(session: Session, week_id: int) -> TrainingWeek | None:
    return session.get(TrainingWeek, week_id)


def get_training_week_with_owner(
    session: Session, week_id: int
) -> tuple[TrainingWeek, int] | None:
    """The training week together with its owning program's `user_id`, in one
    joined query — ownership costs a single round trip regardless of nesting depth.
    """
    statement = (
        select(TrainingWeek, Program.user_id)
        .join(Program, TrainingWeek.program_id == Program.id)  # type: ignore[arg-type]
        .where(TrainingWeek.id == week_id)
    )
    return session.exec(statement).first()  # type: ignore[return-value]


def list_training_weeks_for_program(
    session: Session, program_id: int
) -> list[TrainingWeek]:
    statement = (
        select(TrainingWeek)
        .where(TrainingWeek.program_id == program_id)
        .order_by(TrainingWeek.week_number)  # type: ignore[arg-type]
    )
    return list(session.exec(statement).all())


def get_max_week_number(session: Session, program_id: int) -> int | None:
    return session.exec(
        select(TrainingWeek.week_number)
        .where(TrainingWeek.program_id == program_id)
        .order_by(TrainingWeek.week_number.desc())  # type: ignore[union-attr]
        .limit(1)
    ).first()


def find_by_week_number(
    session: Session, *, program_id: int, week_number: int
) -> TrainingWeek | None:
    statement = select(TrainingWeek).where(
        TrainingWeek.program_id == program_id,
        TrainingWeek.week_number == week_number,
    )
    return session.exec(statement).first()


# Fields callers are allowed to change via update_training_week. An explicit
# allow-list keeps id/program_id from being mass-assigned, same as
# programs_repo.update_program.
_UPDATABLE_FIELDS = {"week_number", "name"}


def update_training_week(
    session: Session, week: TrainingWeek, **fields: Any
) -> TrainingWeek:
    unknown = set(fields) - _UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"update_training_week cannot set fields: {sorted(unknown)}")
    for key, value in fields.items():
        setattr(week, key, value)
    session.add(week)
    session.commit()
    session.refresh(week)
    return week


def delete_training_week(session: Session, week: TrainingWeek) -> None:
    """Permanently remove a training week and its owned tree (WorkoutSession /
    ExercisePrescription cascade via the ORM/DB relationships already configured).
    """
    session.delete(week)
    session.commit()

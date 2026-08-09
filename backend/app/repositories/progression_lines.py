from sqlmodel import Session, select

from app.models.program import Program
from app.models.progression_line import ProgressionLine


def get_progression_line(session: Session, line_id: int) -> ProgressionLine | None:
    return session.get(ProgressionLine, line_id)


def get_progression_line_with_owner(
    session: Session, line_id: int
) -> tuple[ProgressionLine, int] | None:
    """The line together with its owning program's `user_id`, in one joined query
    (line -> program), mirroring
    `exercise_prescriptions_repo.get_exercise_prescription_with_owner`.
    """
    statement = (
        select(ProgressionLine, Program.user_id)
        .join(Program, ProgressionLine.program_id == Program.id)  # type: ignore[arg-type]
        .where(ProgressionLine.id == line_id)
    )
    return session.exec(statement).first()  # type: ignore[return-value]


def list_progression_lines(
    session: Session, *, program_id: int, exercise_id: int
) -> list[ProgressionLine]:
    """All lines for this (program, exercise) pair, default first."""
    statement = (
        select(ProgressionLine)
        .where(
            ProgressionLine.program_id == program_id,
            ProgressionLine.exercise_id == exercise_id,
        )
        .order_by(ProgressionLine.is_default.desc(), ProgressionLine.id)  # type: ignore[union-attr]
    )
    return list(session.exec(statement).all())


def get_default_progression_line(
    session: Session, *, program_id: int, exercise_id: int
) -> ProgressionLine | None:
    statement = select(ProgressionLine).where(
        ProgressionLine.program_id == program_id,
        ProgressionLine.exercise_id == exercise_id,
        ProgressionLine.is_default.is_(True),  # type: ignore[union-attr]
    )
    return session.exec(statement).first()


def create_progression_line(
    session: Session,
    *,
    program_id: int,
    exercise_id: int,
    is_default: bool,
    label: str | None = None,
) -> ProgressionLine:
    line = ProgressionLine(
        program_id=program_id,
        exercise_id=exercise_id,
        is_default=is_default,
        label=label,
    )
    session.add(line)
    session.commit()
    session.refresh(line)
    return line


def update_progression_line_label(
    session: Session, line: ProgressionLine, label: str | None
) -> ProgressionLine:
    line.label = label
    session.add(line)
    session.commit()
    session.refresh(line)
    return line

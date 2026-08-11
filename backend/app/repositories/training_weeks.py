from typing import Any

from sqlmodel import Session, select

from app.models.exercise_prescription import ExercisePrescription
from app.models.program import Program
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession


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


def create_week_from_source(
    session: Session,
    *,
    program_id: int,
    week_number: int,
    name: str | None,
    source_sessions: list[WorkoutSession],
    source_prescriptions: list[ExercisePrescription],
    target_weight_by_prescription_id: dict[int, float | None],
) -> TrainingWeek:
    """Copy `source_sessions`/`source_prescriptions` (already scoped to one source
    week by the caller) into a brand new `TrainingWeek` under `program_id`.

    Same transaction shape as `programs_repo.duplicate_program_tree`: batched
    `add_all()`, one `flush()` per tree level to obtain parent ids, a single
    `commit()` at the end — a partially-committed week would be a corrupt week the
    user has to hunt down and delete by hand. Unlike that function, no
    `ProgressionLine` rows are created or remapped: generation stays inside the same
    program, so every copied prescription's `progression_line_id` is carried forward
    unchanged. No `ExercisePerformance` rows are ever copied.
    """
    new_week = TrainingWeek(program_id=program_id, week_number=week_number, name=name)
    session.add(new_week)
    session.flush()

    new_sessions = [
        WorkoutSession(
            week_id=new_week.id,
            day_name=workout_session.day_name,
            order_index=workout_session.order_index,
            started_at=None,
            completed_at=None,
            notes=None,
        )
        for workout_session in source_sessions
    ]
    session.add_all(new_sessions)
    session.flush()
    session_id_map: dict[int, int] = {
        workout_session.id: new_session.id
        for workout_session, new_session in zip(source_sessions, new_sessions)
    }

    new_prescriptions = [
        ExercisePrescription(
            workout_session_id=session_id_map[prescription.workout_session_id],
            exercise_id=prescription.exercise_id,
            progression_line_id=prescription.progression_line_id,
            order_index=prescription.order_index,
            target_sets=prescription.target_sets,
            target_reps=prescription.target_reps,
            target_weight=target_weight_by_prescription_id[prescription.id],
            target_rpe=prescription.target_rpe,
            progression_type=prescription.progression_type,
            progression_params=(
                dict(prescription.progression_params)
                if prescription.progression_params is not None
                else None
            ),
            notes=prescription.notes,
        )
        for prescription in source_prescriptions
    ]
    session.add_all(new_prescriptions)

    session.commit()
    session.refresh(new_week)
    return new_week

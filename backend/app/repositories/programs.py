from datetime import date, datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models.enums import ProgressionType, WeightUnit
from app.models.exercise_prescription import ExercisePrescription
from app.models.program import Program
from app.models.progression_line import ProgressionLine
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession
from app.repositories import training_weeks as training_weeks_repo
from app.schemas.program_templates import TemplateStructure


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


def duplicate_program_tree(session: Session, *, source: Program, name: str) -> Program:
    """Deep-copy `source`'s planning tree (weeks -> sessions -> prescriptions) and its
    ProgressionLines into a brand new, independent Program. No ExercisePerformance rows
    are ever copied — a duplicate is a new plan, not a copy of training history.

    One transaction, single commit at the end: a partially-committed duplicate would be
    a corrupt program the user would have to hunt down and delete by hand, and per-row
    commits would mean hundreds of round trips for a multi-week program.
    """
    # 1. Read the source tree in flat queries, not by lazy-loading per row.
    weeks = training_weeks_repo.list_training_weeks_for_program(session, source.id)
    week_ids = [week.id for week in weeks]

    sessions: list[WorkoutSession] = []
    if week_ids:
        sessions = list(
            session.exec(
                select(WorkoutSession)
                .where(WorkoutSession.week_id.in_(week_ids))  # type: ignore[attr-defined]
                .order_by(WorkoutSession.week_id, WorkoutSession.order_index)  # type: ignore[union-attr]
            ).all()
        )
    session_ids = [workout_session.id for workout_session in sessions]

    prescriptions: list[ExercisePrescription] = []
    if session_ids:
        prescriptions = list(
            session.exec(
                select(ExercisePrescription)
                .where(ExercisePrescription.workout_session_id.in_(session_ids))  # type: ignore[attr-defined]
                .order_by(
                    ExercisePrescription.workout_session_id,
                    ExercisePrescription.order_index,  # type: ignore[arg-type]
                )
            ).all()
        )

    lines = list(
        session.exec(
            select(ProgressionLine).where(ProgressionLine.program_id == source.id)
        ).all()
    )

    # 2. Create the new Program, always inactive/unarchived regardless of source state.
    new_program = Program(
        user_id=source.user_id,
        name=name,
        description=source.description,
        start_date=None,
        end_date=None,
        is_active=False,
        weight_unit=source.weight_unit,
        default_progression_type=source.default_progression_type,
        default_progression_params=(
            dict(source.default_progression_params)
            if source.default_progression_params is not None
            else None
        ),
        archived_at=None,
    )
    session.add(new_program)
    session.flush()

    # 3. Copy every ProgressionLine, explicitly — ProgressionLine deliberately has no
    # ORM Relationship in either direction (see its model docstring), so nothing here
    # is wired by cascade. Copy all source lines, not only currently-referenced ones.
    new_lines = [
        ProgressionLine(
            program_id=new_program.id,
            exercise_id=line.exercise_id,
            is_default=line.is_default,
            label=line.label,
        )
        for line in lines
    ]
    session.add_all(new_lines)
    session.flush()
    line_id_map: dict[int, int] = {
        line.id: new_line.id for line, new_line in zip(lines, new_lines)
    }

    # 4. Build weeks -> sessions -> prescriptions, flushing once per level (not once
    # per row) to obtain parent ids — SQLAlchemy populates PKs on every pending
    # object at the first flush after add(), so one flush per level is enough.
    new_weeks = [
        TrainingWeek(
            program_id=new_program.id,
            week_number=week.week_number,
            name=week.name,
        )
        for week in weeks
    ]
    session.add_all(new_weeks)
    session.flush()
    week_id_map: dict[int, int] = {
        week.id: new_week.id for week, new_week in zip(weeks, new_weeks)
    }

    new_sessions = [
        WorkoutSession(
            week_id=week_id_map[workout_session.week_id],
            day_name=workout_session.day_name,
            order_index=workout_session.order_index,
            started_at=None,
            completed_at=None,
            notes=None,
        )
        for workout_session in sessions
    ]
    session.add_all(new_sessions)
    session.flush()
    session_id_map: dict[int, int] = {
        workout_session.id: new_session.id
        for workout_session, new_session in zip(sessions, new_sessions)
    }

    for prescription in prescriptions:
        new_prescription = ExercisePrescription(
            workout_session_id=session_id_map[prescription.workout_session_id],
            exercise_id=prescription.exercise_id,
            progression_line_id=line_id_map[prescription.progression_line_id],
            order_index=prescription.order_index,
            target_sets=prescription.target_sets,
            target_reps=prescription.target_reps,
            target_weight=prescription.target_weight,
            target_rpe=prescription.target_rpe,
            progression_type=prescription.progression_type,
            progression_params=(
                dict(prescription.progression_params)
                if prescription.progression_params is not None
                else None
            ),
            notes=prescription.notes,
        )
        session.add(new_prescription)

    # 5. prescription.performances is never traversed — no ExercisePerformance rows
    # are created for the duplicate.

    # 6. Single commit at the end.
    session.commit()
    session.refresh(new_program)
    return new_program


def create_program_from_template_structure(
    session: Session,
    *,
    user_id: int,
    name: str,
    weight_unit: WeightUnit,
    description: str | None,
    default_progression_type: ProgressionType | None,
    default_progression_params: dict | None,
    structure: TemplateStructure,
    exercise_id_by_name: dict[str, int],
) -> Program:
    """Build a brand new, caller-owned `Program` tree (ProgressionLines + weeks ->
    sessions -> prescriptions) from a validated template `structure`. Same
    transaction shape as `duplicate_program_tree` — batched with `add_all()`, one
    flush per tree level, single `commit()` at the end — but reads from a validated
    JSONB structure instead of a live source `Program`, so it is not built by
    parameterizing `duplicate_program_tree` (see TRAIN-24's design plan: the two
    read from unlike sources, and TRAIN-23 already ruled out pre-abstracting a
    shared copy helper across unwritten call sites).

    The template row itself is never read here beyond what the caller already
    resolved into `structure`/`exercise_id_by_name` — nothing in this function
    writes to `program_templates`, which is what makes "generation never mutates
    the template" true by construction.
    """
    # 1. Create the Program, always inactive/unarchived with open dates — same
    # starting state as a fresh duplicate.
    new_program = Program(
        user_id=user_id,
        name=name,
        description=description,
        start_date=None,
        end_date=None,
        is_active=False,
        weight_unit=weight_unit,
        default_progression_type=default_progression_type,
        default_progression_params=(
            dict(default_progression_params)
            if default_progression_params is not None
            else None
        ),
        archived_at=None,
    )
    session.add(new_program)
    session.flush()

    # 2. Create ProgressionLines first, one per distinct (exercise_id, line_key)
    # pair encountered while walking the structure. line_key is None -> that
    # exercise's default line; a non-null line_key -> an explicit split line.
    # ProgressionLine has no ORM Relationship in either direction (see its model
    # docstring), so this id map must be built and threaded through explicitly.
    line_specs: dict[tuple[int, str | None], str | None] = {}
    for week in structure.weeks:
        for workout_session in week.sessions:
            for prescription in workout_session.prescriptions:
                exercise_id = exercise_id_by_name[prescription.exercise_name]
                key = (exercise_id, prescription.line_key)
                if key not in line_specs:
                    line_specs[key] = prescription.line_label
                elif line_specs[key] != prescription.line_label:
                    # Two prescriptions in the same (exercise, line_key) group
                    # disagreeing on the label is a seed-integrity bug: they'd
                    # collapse onto one ProgressionLine row, and silently keeping
                    # whichever label was seen first would hide the conflict
                    # rather than surface it.
                    raise ValueError(
                        f"Conflicting line_label for exercise_id={exercise_id} "
                        f"line_key={prescription.line_key!r}: "
                        f"{line_specs[key]!r} vs {prescription.line_label!r}"
                    )

    new_lines = [
        ProgressionLine(
            program_id=new_program.id,
            exercise_id=exercise_id,
            is_default=line_key is None,
            label=label,
        )
        for (exercise_id, line_key), label in line_specs.items()
    ]
    session.add_all(new_lines)
    session.flush()
    line_id_map: dict[tuple[int, str | None], int] = {
        spec_key: new_line.id
        for spec_key, new_line in zip(line_specs.keys(), new_lines)
    }

    # 3. Weeks -> sessions -> prescriptions, add_all() + flush() per level.
    new_weeks = [
        TrainingWeek(
            program_id=new_program.id,
            week_number=week.week_number,
            name=week.name,
        )
        for week in structure.weeks
    ]
    session.add_all(new_weeks)
    session.flush()

    new_sessions: list[WorkoutSession] = []
    for week_index, week in enumerate(structure.weeks):
        for workout_session in week.sessions:
            new_sessions.append(
                WorkoutSession(
                    week_id=new_weeks[week_index].id,
                    day_name=workout_session.day_name,
                    order_index=workout_session.order_index,
                    started_at=None,
                    completed_at=None,
                    notes=None,
                )
            )
    session.add_all(new_sessions)
    session.flush()

    # 4. Prescriptions, resolving exercise_id and progression_line_id per row.
    new_prescriptions: list[ExercisePrescription] = []
    session_cursor = 0
    for week in structure.weeks:
        for workout_session in week.sessions:
            new_session_row = new_sessions[session_cursor]
            session_cursor += 1
            for prescription in workout_session.prescriptions:
                exercise_id = exercise_id_by_name[prescription.exercise_name]
                line_id = line_id_map[(exercise_id, prescription.line_key)]
                progression_params = (
                    prescription.progression_params.model_dump(exclude_unset=True)
                    if prescription.progression_params is not None
                    else None
                )
                new_prescriptions.append(
                    ExercisePrescription(
                        workout_session_id=new_session_row.id,
                        exercise_id=exercise_id,
                        progression_line_id=line_id,
                        order_index=prescription.order_index,
                        target_sets=prescription.target_sets,
                        target_reps=prescription.target_reps,
                        target_weight=None,
                        target_rpe=prescription.target_rpe,
                        progression_type=prescription.progression_type,
                        progression_params=progression_params,
                        notes=prescription.notes,
                    )
                )
    session.add_all(new_prescriptions)

    # 5. Single commit at the end — a partial commit would leave a corrupt
    # half-generated program the user has to delete by hand.
    session.commit()
    session.refresh(new_program)
    return new_program

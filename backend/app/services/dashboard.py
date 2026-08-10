"""Dashboard aggregation (TRAIN-22): a read-only layer over the progression
engine (TRAIN-20) and training-history analytics (TRAIN-21) landed earlier.
Mutates nothing.

Two layers, same split `app/services/history.py` and `app/services/progression.py`
already document:

- `resolve_program_status` and `fold_exercise_history` are **pure functions** —
  no `Session`, no I/O. `resolve_program_status` is deliberately the branchiest
  logic in this ticket (next-workout resolution, per TRAIN-22's design plan
  "Resolved question 1"), so it's kept out of SQL and unit-testable without a
  DB.
- `get_dashboard` does the DB-touching orchestration: one query per piece of
  the payload (see the design plan's "Query budget"), then delegates to the
  pure functions above.

PR/e1RM math is never reimplemented here — `best_effort`, `detect_new_records`,
`to_kg`/`from_kg`, and `personal_record_read` are reused directly from
`app/services/history.py`, per TRAIN-22's design plan: "Two implementations of
Epley is exactly the correctness hazard TRAIN-21 called out."
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from app.models.enums import WeightUnit
from app.repositories import dashboard as dashboard_repo
from app.repositories import history as history_repo
from app.repositories import programs as programs_repo
from app.schemas.dashboard import (
    ActiveProgramRead,
    ConsistencyRead,
    ConsistencyRollingWindow,
    DashboardRead,
    ExerciseTrendRead,
    NextWorkoutRead,
    ProgramProgressCounts,
    ProgramProgressRead,
)
from app.schemas.history import PersonalRecordRead
from app.services.history import (
    BestEffort,
    PerformanceRecord,
    RecordHit,
    best_effort,
    detect_new_records,
    from_kg,
    personal_record_read,
    row_to_record,
)

# Module-level constants, not query params — nothing in the ticket asks for
# these to be configurable. See TRAIN-22's design plan, "Other decisions".
RECENT_WINDOW_DAYS = 28
SHORT_WINDOW_DAYS = 7


# --------------------------------------------------------------------------
# Pure core — no Session, no I/O.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProgramSessionRow:
    """One session of the active program, as narrowed by
    `dashboard_repo.list_program_sessions`.
    """

    id: int
    week_id: int
    week_number: int
    order_index: int
    day_name: str
    started_at: datetime | None
    completed_at: datetime | None
    prescription_count: int


@dataclass(frozen=True)
class ProgramStatus:
    next_workout: ProgramSessionRow | None
    program_complete: bool
    sessions_completed: int
    sessions_total: int
    current_week_number: int | None
    current_week_sessions_completed: int
    current_week_sessions_total: int


def resolve_program_status(sessions: list[ProgramSessionRow]) -> ProgramStatus:
    """Next-workout resolution: resume, then continue — see TRAIN-22's design
    plan, "Resolved question 1" for the full algorithm and its rationale. Pure:
    no DB, no I/O, so this branchiest piece of the ticket is unit-testable
    without a DB.

    An empty `sessions` list (a program with zero sessions) reports
    `next_workout=None`, `program_complete=False` — an empty program is not a
    finished one.
    """
    if not sessions:
        return ProgramStatus(
            next_workout=None,
            program_complete=False,
            sessions_completed=0,
            sessions_total=0,
            current_week_number=None,
            current_week_sessions_completed=0,
            current_week_sessions_total=0,
        )

    ordered = sorted(sessions, key=lambda s: (s.week_number, s.order_index, s.id))
    sessions_total = len(ordered)
    sessions_completed = sum(1 for s in ordered if s.completed_at is not None)

    in_progress = [
        s for s in ordered if s.started_at is not None and s.completed_at is None
    ]
    completed = [s for s in ordered if s.completed_at is not None]

    next_workout: ProgramSessionRow | None
    program_complete: bool

    if in_progress:
        # Resume wins. If more than one is somehow in progress, take the
        # earliest in program order (nothing enforces single-in-progress today).
        next_workout = in_progress[0]
        program_complete = False
    elif completed:
        cursor = max(completed, key=lambda s: (s.completed_at, s.id))
        cursor_position = (cursor.week_number, cursor.order_index, cursor.id)
        remaining = [
            s
            for s in ordered
            if s.completed_at is None
            and (s.week_number, s.order_index, s.id) > cursor_position
        ]
        if remaining:
            next_workout = remaining[0]
            program_complete = False
        else:
            # Nothing not-completed follows the cursor. Sessions skipped
            # earlier in the program are passed over permanently and never
            # resurface — that's the deliberate, visible consequence of
            # "resume, then continue" (see the design plan). They still show
            # up in sessions_completed/sessions_total, just not here.
            next_workout = None
            program_complete = True
    else:
        # Nothing has ever been completed — the first not-completed session
        # in ascending order.
        not_completed = [s for s in ordered if s.completed_at is None]
        next_workout = not_completed[0] if not_completed else None
        program_complete = False

    if next_workout is not None:
        current_week_number = next_workout.week_number
    elif completed:
        current_week_number = max(
            completed, key=lambda s: (s.completed_at, s.id)
        ).week_number
    else:
        current_week_number = ordered[0].week_number

    current_week_sessions = [s for s in ordered if s.week_number == current_week_number]

    return ProgramStatus(
        next_workout=next_workout,
        program_complete=program_complete,
        sessions_completed=sessions_completed,
        sessions_total=sessions_total,
        current_week_number=current_week_number,
        current_week_sessions_completed=sum(
            1 for s in current_week_sessions if s.completed_at is not None
        ),
        current_week_sessions_total=len(current_week_sessions),
    )


@dataclass(frozen=True)
class ExerciseFold:
    """One exercise's PR hits within the recent window, plus the two bests the
    trend delta is computed from.
    """

    hits: list[RecordHit]
    best_in_window: BestEffort | None
    best_before_window: BestEffort | None


def fold_exercise_history(
    records: list[PerformanceRecord], *, window_start: datetime
) -> ExerciseFold:
    """One exercise's lifetime records (any order), folded in a single
    chronological pass into: PRs actually set within the window (each compared
    against the true bests as of immediately before its own session — the same
    "at session completion" moment `history_service.get_session_personal_records`
    uses, just walked across every in-window session instead of one target
    session), and the best-e1RM-in-window / best-e1RM-before-window pair the
    trend delta needs. Pure: no DB, no I/O.

    `window_start` is inclusive — a session completed exactly at the boundary
    counts as "within the window".
    """
    by_session: dict[int, list[PerformanceRecord]] = defaultdict(list)
    for record in records:
        by_session[record.workout_session_id].append(record)

    sessions_ascending = sorted(
        by_session.items(), key=lambda kv: (kv[1][0].performed_at, kv[0])
    )

    hits: list[RecordHit] = []
    prior_records: list[PerformanceRecord] = []
    window_records: list[PerformanceRecord] = []
    best_before_window: BestEffort | None = None
    captured_before_window = False

    for _, session_records in sessions_ascending:
        session_completed_at = session_records[0].performed_at
        in_window = session_completed_at >= window_start

        if in_window and not captured_before_window:
            best_before_window = best_effort(prior_records)
            captured_before_window = True

        if in_window:
            prior_best = best_effort(prior_records)
            session_best = best_effort(session_records)
            hits.extend(detect_new_records(session_best, prior_best))
            window_records.extend(session_records)

        prior_records.extend(session_records)

    if not captured_before_window:
        # No session ever reached the window — every record predates it.
        # Callers only fold exercises selected for having been trained in the
        # window, so this is defensive rather than expected.
        best_before_window = best_effort(prior_records)

    return ExerciseFold(
        hits=hits,
        best_in_window=best_effort(window_records),
        best_before_window=best_before_window,
    )


# --------------------------------------------------------------------------
# Orchestration — Session, ownership scoping, row fetch, then delegate up.
# --------------------------------------------------------------------------


def _row_to_program_session(row: tuple) -> ProgramSessionRow:
    workout_session, week_number, prescription_count = row
    return ProgramSessionRow(
        id=workout_session.id,
        week_id=workout_session.week_id,
        week_number=week_number,
        order_index=workout_session.order_index,
        day_name=workout_session.day_name,
        started_at=workout_session.started_at,
        completed_at=workout_session.completed_at,
        prescription_count=prescription_count,
    )


def _program_progress_read(status: ProgramStatus) -> ProgramProgressRead:
    return ProgramProgressRead(
        program=ProgramProgressCounts(
            sessions_completed=status.sessions_completed,
            sessions_total=status.sessions_total,
        ),
        current_week=ProgramProgressCounts(
            sessions_completed=status.current_week_sessions_completed,
            sessions_total=status.current_week_sessions_total,
        ),
    )


def _next_workout_read(session_row: ProgramSessionRow) -> NextWorkoutRead:
    status = "in_progress" if session_row.started_at is not None else "not_started"
    return NextWorkoutRead(
        id=session_row.id,
        week_id=session_row.week_id,
        week_number=session_row.week_number,
        day_name=session_row.day_name,
        order_index=session_row.order_index,
        status=status,  # type: ignore[arg-type]
        prescription_count=session_row.prescription_count,
    )


def _rolling_window_read(
    *,
    completed_at_last_28_days: list[datetime],
    last_completed_at: datetime | None,
    now: datetime,
) -> ConsistencyRollingWindow:
    seven_day_cutoff = now - timedelta(days=SHORT_WINDOW_DAYS)
    sessions_completed_last_7_days = sum(
        1
        for completed_at in completed_at_last_28_days
        if completed_at >= seven_day_cutoff
    )
    days_since_last_session = (
        (now - last_completed_at).days if last_completed_at is not None else None
    )
    return ConsistencyRollingWindow(
        sessions_completed_last_7_days=sessions_completed_last_7_days,
        sessions_completed_last_28_days=len(completed_at_last_28_days),
        days_since_last_session=days_since_last_session,
    )


def _exercise_trend_read(
    *,
    exercise_id: int,
    exercise_name: str,
    fold: ExerciseFold,
    display_unit: WeightUnit,
) -> ExerciseTrendRead | None:
    """`None` when the exercise has no weighted e1RM within the window at all —
    nothing to show a trend for (e.g. a bodyweight-only exercise, or one whose
    only in-window sets didn't produce a valid e1RM).
    """
    if fold.best_in_window is None or fold.best_in_window.best_one_rm is None:
        return None

    in_window_effort = fold.best_in_window.best_one_rm
    best_in_window_display = round(
        from_kg(in_window_effort.one_rm_kg, display_unit),
        2,  # type: ignore[arg-type]
    )

    before_effort = (
        fold.best_before_window.best_one_rm
        if fold.best_before_window is not None
        else None
    )
    if before_effort is None:
        best_before_window_display = None
        delta = None
    else:
        best_before_window_display = round(
            from_kg(before_effort.one_rm_kg, display_unit),
            2,  # type: ignore[arg-type]
        )
        delta = round(best_in_window_display - best_before_window_display, 2)

    return ExerciseTrendRead(
        exercise_id=exercise_id,
        exercise_name=exercise_name,
        best_one_rm_in_window=best_in_window_display,
        best_one_rm_before_window=best_before_window_display,
        delta=delta,
        display_unit=display_unit,
    )


def get_dashboard(
    session: Session, *, user_id: int, display_unit: WeightUnit
) -> DashboardRead:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=RECENT_WINDOW_DAYS)

    # 1. Active program.
    program = programs_repo.get_active_program(session, user_id)

    active_program: ActiveProgramRead | None = None
    program_progress: ProgramProgressRead | None = None
    next_workout: NextWorkoutRead | None = None
    program_complete = False

    if program is not None:
        # 2. The active program's sessions — feeds next_workout,
        # program_complete, program_progress, and current_week_number in one
        # shot (see the design plan's "Query budget").
        rows = dashboard_repo.list_program_sessions(session, program_id=program.id)
        program_sessions = [_row_to_program_session(row) for row in rows]
        status = resolve_program_status(program_sessions)

        active_program = ActiveProgramRead(
            id=program.id,  # type: ignore[arg-type]
            name=program.name,
            weight_unit=program.weight_unit,
            start_date=program.start_date,
            end_date=program.end_date,
            current_week_number=status.current_week_number,
        )
        program_progress = _program_progress_read(status)
        program_complete = status.program_complete
        if status.next_workout is not None:
            next_workout = _next_workout_read(status.next_workout)

    # 3. Completed-session counts over the 7/28-day windows, plus the last
    # completed_at, across all programs.
    completed_at_last_28_days = dashboard_repo.list_completed_at_since(
        session, user_id=user_id, since=window_start
    )
    last_completed_at = dashboard_repo.get_last_completed_at(session, user_id=user_id)
    rolling_window = _rolling_window_read(
        completed_at_last_28_days=completed_at_last_28_days,
        last_completed_at=last_completed_at,
        now=now,
    )

    consistency = ConsistencyRead(
        program_progress=program_progress, rolling_window=rolling_window
    )

    # 4. Distinct exercise ids trained in the recent window.
    exercise_ids = dashboard_repo.list_recent_exercise_ids(
        session, user_id=user_id, since=window_start
    )

    recent_personal_records: list[PersonalRecordRead] = []
    exercise_trends: list[ExerciseTrendRead] = []

    if exercise_ids:
        # 5. Every counted set for those exercises, lifetime, in one query.
        rows = history_repo.list_weighted_performances_for_exercises(
            session, user_id=user_id, exercise_ids=exercise_ids
        )
        records_by_exercise: dict[int, list[PerformanceRecord]] = defaultdict(list)
        name_by_exercise: dict[int, str] = {}
        for row in rows:
            exercise_id, exercise_name, *record_row = row
            records_by_exercise[exercise_id].append(row_to_record(tuple(record_row)))
            name_by_exercise[exercise_id] = exercise_name

        for exercise_id, records in records_by_exercise.items():
            exercise_name = name_by_exercise[exercise_id]
            fold = fold_exercise_history(records, window_start=window_start)

            for hit in fold.hits:
                recent_personal_records.append(
                    personal_record_read(
                        exercise_id=exercise_id,
                        exercise_name=exercise_name,
                        kind=hit.kind,
                        effort=hit.effort,
                        display_unit=display_unit,
                    )
                )

            trend = _exercise_trend_read(
                exercise_id=exercise_id,
                exercise_name=exercise_name,
                fold=fold,
                display_unit=display_unit,
            )
            if trend is not None:
                exercise_trends.append(trend)

    recent_personal_records.sort(key=lambda pr: pr.performed_at, reverse=True)
    exercise_trends.sort(key=lambda t: t.exercise_name)

    return DashboardRead(
        active_program=active_program,
        program_progress=program_progress,
        next_workout=next_workout,
        program_complete=program_complete,
        consistency=consistency,
        recent_personal_records=recent_personal_records,
        exercise_trends=exercise_trends,
    )

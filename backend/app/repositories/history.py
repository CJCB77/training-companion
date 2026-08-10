"""Read-only queries backing the history/PR/e1RM-trend endpoints (TRAIN-21).

Every query here narrows rows only — no aggregation, no Epley math. Reduction
(picking the heaviest lift, the best e1RM, whether a session beat the prior
bests) is `app/services/history.py`'s job, per CLAUDE.md: "Epley lives in
Python only, never duplicated as a SQL expression."
"""

from sqlmodel import Session, select

from app.models.enums import SetCompletionState
from app.models.exercise import Exercise
from app.models.exercise_performance import ExercisePerformance
from app.models.exercise_prescription import ExercisePrescription
from app.models.program import Program
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession

# Sets that genuinely happened and produced a countable result. SKIPPED is
# excluded — never performed. A FAILED set still records reps genuinely
# performed (140x4 when 5 were targeted is a real 140x4).
_COUNTED_STATES = (SetCompletionState.COMPLETED, SetCompletionState.FAILED)


def list_completed_sessions(
    session: Session,
    *,
    user_id: int,
    program_id: int | None,
    limit: int,
    offset: int,
) -> list[tuple[WorkoutSession, int]]:
    """Completed sessions (`completed_at IS NOT NULL`) the user owns, newest
    first by `completed_at` then by `id` (secondary key: `completed_at` alone
    isn't unique, so same-instant completions still need a deterministic order
    or pagination can duplicate/skip a row across a page boundary), each paired
    with its `program_id`. Same prescription/session/week/program join chain
    used throughout this codebase (see
    `exercise_prescriptions_repo.list_prior_attempts`), minus the prescription
    hop since sessions don't need it.

    Archived programs are included (data stays fully retained for history —
    see CLAUDE.md's Entity Lifecycle Conventions); deleted ones cascade their
    sessions away, so they never appear here regardless.
    """
    statement = (
        select(WorkoutSession, TrainingWeek.program_id)
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .join(Program, TrainingWeek.program_id == Program.id)  # type: ignore[arg-type]
        .where(
            Program.user_id == user_id,
            WorkoutSession.completed_at.is_not(None),  # type: ignore[union-attr]
        )
    )
    if program_id is not None:
        statement = statement.where(TrainingWeek.program_id == program_id)
    statement = (
        statement.order_by(
            WorkoutSession.completed_at.desc(),  # type: ignore[union-attr]
            WorkoutSession.id.desc(),  # type: ignore[union-attr]
        )
        .limit(limit)
        .offset(offset)
    )
    return list(session.exec(statement).all())  # type: ignore[return-value]


def list_weighted_performances_for_exercise(
    session: Session, *, user_id: int, exercise_id: int
) -> list[tuple]:
    """Every counted weighted set logged for `exercise_id`, across **all** of the
    user's programs (any unit, any progression line), newest session first —
    ordered by `WorkoutSession.completed_at`, then `WorkoutSession.id`, then
    `ExercisePerformance.id`, so both same-instant sessions and same-session
    sets come back in a stable, repeatable row order. This alone only freezes
    "whichever set was logged first" as the row order — `best_effort`'s own
    tie-break keys (see `app/services/history.py`) are what actually decide
    ties correctly (e.g. 100x5 over 100x3 at equal weight); this ordering
    just makes that reduction's input reproducible run to run.

    "Counted" per TRAIN-21's design plan: session completed, `actual_weight IS
    NOT NULL`, `actual_reps >= 1`, state COMPLETED or FAILED. Bodyweight work
    (`actual_weight IS NULL`) is excluded — it can't feed a weight-based PR or
    e1RM.

    Deliberately global (not program-scoped): lifetime PRs and the e1RM trend
    both need every program the exercise was ever trained in — that's the
    whole reason this reintroduces cross-unit conversion (see
    `app/services/history.py`). Callers that want a single program's slice
    (the trend endpoint's optional `program_id` filter) narrow the result
    in Python rather than adding a second query shape here.

    Returns raw rows — `(actual_weight, actual_reps, weight_unit,
    completed_at, workout_session_id, program_id, progression_line_id)` — for
    the service to turn into `PerformanceRecord`s. Not a `select(...)` of a
    whole model, so no ORM identity map benefit is lost by returning tuples.
    """
    statement = (
        select(
            ExercisePerformance.actual_weight,
            ExercisePerformance.actual_reps,
            Program.weight_unit,
            WorkoutSession.completed_at,
            WorkoutSession.id,
            Program.id,
            ExercisePrescription.progression_line_id,
        )
        .join(
            ExercisePrescription,
            ExercisePerformance.prescription_id == ExercisePrescription.id,  # type: ignore[arg-type]
        )
        .join(
            WorkoutSession,
            ExercisePrescription.workout_session_id == WorkoutSession.id,  # type: ignore[arg-type]
        )
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .join(Program, TrainingWeek.program_id == Program.id)  # type: ignore[arg-type]
        .where(
            Program.user_id == user_id,
            ExercisePrescription.exercise_id == exercise_id,
            WorkoutSession.completed_at.is_not(None),  # type: ignore[union-attr]
            ExercisePerformance.actual_weight.is_not(None),  # type: ignore[union-attr]
            ExercisePerformance.actual_reps >= 1,
            ExercisePerformance.completion_state.in_(_COUNTED_STATES),  # type: ignore[attr-defined]
        )
        .order_by(
            WorkoutSession.completed_at.desc(),  # type: ignore[union-attr]
            WorkoutSession.id.desc(),  # type: ignore[union-attr]
            ExercisePerformance.id,  # type: ignore[arg-type]
        )
    )
    return list(session.exec(statement).all())


def list_weighted_performances_for_exercises(
    session: Session, *, user_id: int, exercise_ids: list[int]
) -> list[tuple]:
    """Batched sibling of `list_weighted_performances_for_exercise` — TRAIN-22's
    dashboard needs the lifetime history of several exercises trained in the
    recent window, and looping the singular query once per exercise would be an
    N+1. Same "counted set" rules as the singular query.

    Two differences from the singular query's row shape, both a consequence of
    covering more than one exercise per call: `ExercisePrescription.exercise_id`
    and `Exercise.name` are added so the caller can group rows back out per
    exercise, and rows come back **oldest first** (`completed_at` ascending)
    rather than newest first — TRAIN-22's fold walks each exercise's history
    chronologically to detect PRs and the trend delta, rather than doing the
    single "reduce to one best" pass the singular query's callers use.

    Returns `(exercise_id, exercise_name, actual_weight, actual_reps,
    weight_unit, completed_at, workout_session_id, program_id,
    progression_line_id)` rows. `[]` for an empty `exercise_ids` — no query
    executes.
    """
    if not exercise_ids:
        return []
    statement = (
        select(
            ExercisePrescription.exercise_id,
            Exercise.name,
            ExercisePerformance.actual_weight,
            ExercisePerformance.actual_reps,
            Program.weight_unit,
            WorkoutSession.completed_at,
            WorkoutSession.id,
            Program.id,
            ExercisePrescription.progression_line_id,
        )
        .join(
            ExercisePrescription,
            ExercisePerformance.prescription_id == ExercisePrescription.id,  # type: ignore[arg-type]
        )
        .join(Exercise, ExercisePrescription.exercise_id == Exercise.id)  # type: ignore[arg-type]
        .join(
            WorkoutSession,
            ExercisePrescription.workout_session_id == WorkoutSession.id,  # type: ignore[arg-type]
        )
        .join(TrainingWeek, WorkoutSession.week_id == TrainingWeek.id)  # type: ignore[arg-type]
        .join(Program, TrainingWeek.program_id == Program.id)  # type: ignore[arg-type]
        .where(
            Program.user_id == user_id,
            ExercisePrescription.exercise_id.in_(exercise_ids),  # type: ignore[attr-defined]
            WorkoutSession.completed_at.is_not(None),  # type: ignore[union-attr]
            ExercisePerformance.actual_weight.is_not(None),  # type: ignore[union-attr]
            ExercisePerformance.actual_reps >= 1,
            ExercisePerformance.completion_state.in_(_COUNTED_STATES),  # type: ignore[attr-defined]
        )
        .order_by(
            WorkoutSession.completed_at,  # type: ignore[union-attr]
            WorkoutSession.id,  # type: ignore[union-attr]
            ExercisePerformance.id,  # type: ignore[arg-type]
        )
    )
    return list(session.exec(statement).all())

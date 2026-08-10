"""Training history, PR detection, and estimated-1RM trends (TRAIN-21).

Read-only analytics over `ExercisePerformance` data landed by TRAIN-19. Two
layers, deliberately split — same pattern `app/services/progression.py`
documents:

- `estimate_one_rm`, `to_kg`, `from_kg`, `best_effort`, `detect_new_records`
  are **pure functions** — no `Session`, no I/O — satisfying the acceptance
  criterion that 1RM calculation be unit-testable in isolation. Most of
  TRAIN-21's tests hit these directly.
- `list_completed_sessions`, `get_personal_records`,
  `get_session_personal_records`, and `get_one_rm_trend` do the DB-touching
  orchestration: ownership checks, row fetch, then delegate to the pure
  functions.

PRs are computed on demand, never stored — see TRAIN-21's design plan, "Other
decisions". "Was this a PR" is derived as "beat everything completed strictly
before this session's `completed_at`", which is idempotent and re-derivable;
a stored flag would drift the moment a performance is edited or deleted.

Unit conversion (this is the one place in the codebase that reintroduces it —
see the module-level note in `app/models/profile.py` and CLAUDE.md's
`Program.weight_unit` comment) lives here rather than a shared
`core/units.py`; extract only if a second real caller appears.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session

from app.models.enums import PersonalRecordKind, WeightUnit
from app.repositories import exercise_prescriptions as exercise_prescriptions_repo
from app.repositories import exercises as exercises_repo
from app.repositories import history as history_repo
from app.schemas.history import (
    CompletedSessionRead,
    OneRmTrendPointRead,
    PersonalRecordRead,
)
from app.services import programs as programs_service
from app.services import workout_sessions as workout_sessions_service

# Re-exported so callers (routes) don't have to reach into the underlying
# services directly to catch these — same pattern api/progression.py uses.
ProgramNotFoundError = programs_service.ProgramNotFoundError
ProgramAccessDeniedError = programs_service.ProgramAccessDeniedError
WorkoutSessionNotFoundError = workout_sessions_service.WorkoutSessionNotFoundError
WorkoutSessionAccessDeniedError = (
    workout_sessions_service.WorkoutSessionAccessDeniedError
)


class ExerciseNotFoundError(Exception):
    """No exercise exists with that id, or it isn't visible to this user."""


# The exact international avoirdupois pound. Divide, never multiply by a
# reciprocal, for the reverse direction — keeps rounding behavior symmetric.
_LB_TO_KG = 0.45359237

# A new PR must clear the incumbent by more than this, in kg. Absorbs the
# last-bit float noise a cross-unit conversion can introduce; matching an
# existing best is not a PR. The common case — both values logged in the same
# unit — never converts at all, so no drift is possible there.
_PR_EPSILON_KG = 1e-6

DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200


# --------------------------------------------------------------------------
# Pure core — no Session, no I/O.
# --------------------------------------------------------------------------


def estimate_one_rm(weight: float, reps: int) -> float | None:
    """Epley: weight * (1 + reps / 30). `reps == 1` returns `weight` unchanged —
    raw Epley would inflate a true single by 3.3%. `reps < 1` returns `None`
    (no such set exists). No high-rep cap — that would be an unrequested
    business rule.

    Unit-agnostic: `estimate_one_rm(to_kg(w), r) == to_kg(estimate_one_rm(w, r))`,
    since Epley is linear in weight. Callers may compute it in whatever unit
    `weight` is already in.
    """
    if reps < 1:
        return None
    if reps == 1:
        return weight
    return weight * (1 + reps / 30)


def to_kg(weight: float, unit: WeightUnit) -> float:
    """Comparison-unit conversion — internal only, never rounded. See
    "Resolved question 2" in TRAIN-21's design plan.
    """
    if unit == WeightUnit.KG:
        return weight
    return weight * _LB_TO_KG


def from_kg(weight_kg: float, unit: WeightUnit) -> float:
    if unit == WeightUnit.KG:
        return weight_kg
    return weight_kg / _LB_TO_KG


@dataclass(frozen=True)
class PerformanceRecord:
    """One counted set, as narrowed by `history_repo.list_weighted_performances_for_exercise`."""

    weight: float
    reps: int
    weight_unit: WeightUnit
    performed_at: datetime
    workout_session_id: int
    program_id: int
    progression_line_id: int


@dataclass(frozen=True)
class Effort:
    """A `PerformanceRecord` with its comparison (kg) and as-logged e1RM
    already computed. `weight_kg` decides `heaviest_weight` winners;
    `one_rm_kg` decides `best_estimated_one_rm` winners. `one_rm` is the e1RM
    computed directly in `weight_unit` (never round-tripped through kg), so it
    can be returned as-logged.
    """

    weight: float
    reps: int
    weight_unit: WeightUnit
    performed_at: datetime
    workout_session_id: int
    program_id: int
    progression_line_id: int
    weight_kg: float
    one_rm: float | None
    one_rm_kg: float | None


@dataclass(frozen=True)
class BestEffort:
    """The best weight effort and best e1RM effort within one group of
    records — a session's sets, or every set an exercise has ever had.
    """

    best_weight: Effort | None
    best_one_rm: Effort | None


@dataclass(frozen=True)
class RecordHit:
    kind: PersonalRecordKind
    effort: Effort


def _to_effort(record: PerformanceRecord) -> Effort:
    one_rm = estimate_one_rm(record.weight, record.reps)
    return Effort(
        weight=record.weight,
        reps=record.reps,
        weight_unit=record.weight_unit,
        performed_at=record.performed_at,
        workout_session_id=record.workout_session_id,
        program_id=record.program_id,
        progression_line_id=record.progression_line_id,
        weight_kg=to_kg(record.weight, record.weight_unit),
        one_rm=one_rm,
        one_rm_kg=to_kg(one_rm, record.weight_unit) if one_rm is not None else None,
    )


def best_effort(records: list[PerformanceRecord]) -> BestEffort | None:
    """Reduces a set list to its best weight and best e1RM. Pure: no DB, no I/O.
    `None` for an empty input; every counted record has a computable e1RM (a
    `PerformanceRecord` never carries `reps < 1`), so `best_one_rm` is only
    `None` when `records` is empty.

    Deterministic regardless of the caller's input order or row order *within*
    a session, on two levels:

    - The `max()` sort keys are total, not just the primary (weight_kg /
      one_rm_kg) figure — `best_weight` breaks ties by `reps` (at equal
      weight, more reps is the semantically better effort: 100x5 beats
      100x3), and `best_one_rm` breaks ties by `weight_kg`. This is what
      makes a same-session tie deterministic (e.g. a 5x5 where the last set
      fails at reduced reps — `FAILED` sets are counted — leaves every set
      tied on weight; without the `reps` tiebreak, 100x3 could win over 100x5
      depending on row order alone).
    - Records are still sorted oldest-first before reducing, so if two
      efforts are tied on *both* keys (the same weight and the same reps,
      logged in different sessions), `max()` — which returns the first
      maximal element it sees — resolves to the *earliest* occurrence rather
      than whichever the repository happened to return first.
    """
    if not records:
        return None
    ordered = sorted(records, key=lambda r: (r.performed_at, r.workout_session_id))
    efforts = [_to_effort(r) for r in ordered]
    best_weight = max(efforts, key=lambda e: (e.weight_kg, e.reps))
    one_rm_efforts = [e for e in efforts if e.one_rm_kg is not None]
    best_one_rm = (
        max(one_rm_efforts, key=lambda e: (e.one_rm_kg, e.weight_kg))
        if one_rm_efforts
        else None
    )
    return BestEffort(best_weight=best_weight, best_one_rm=best_one_rm)


def detect_new_records(
    session_best: BestEffort | None, prior_best: BestEffort | None
) -> list[RecordHit]:
    """Compares one session's efforts against the pre-session bests and returns
    what was beaten. Pure: no DB, no I/O.

    A `None` `prior_best` (nothing logged before this session) means anything
    in `session_best` is automatically a record. Matching an existing best
    (within `_PR_EPSILON_KG`) is not a PR.
    """
    if session_best is None:
        return []
    hits: list[RecordHit] = []

    prior_weight_kg = (
        prior_best.best_weight.weight_kg
        if prior_best is not None and prior_best.best_weight is not None
        else None
    )
    if session_best.best_weight is not None and (
        prior_weight_kg is None
        or session_best.best_weight.weight_kg > prior_weight_kg + _PR_EPSILON_KG
    ):
        hits.append(
            RecordHit(
                kind=PersonalRecordKind.HEAVIEST_WEIGHT, effort=session_best.best_weight
            )
        )

    prior_one_rm_kg = (
        prior_best.best_one_rm.one_rm_kg
        if prior_best is not None and prior_best.best_one_rm is not None
        else None
    )
    if session_best.best_one_rm is not None and (
        prior_one_rm_kg is None
        or session_best.best_one_rm.one_rm_kg > prior_one_rm_kg + _PR_EPSILON_KG
    ):
        hits.append(
            RecordHit(
                kind=PersonalRecordKind.BEST_ESTIMATED_ONE_RM,
                effort=session_best.best_one_rm,
            )
        )
    return hits


# --------------------------------------------------------------------------
# Orchestration — Session, ownership checks, row fetch, then delegate up.
# --------------------------------------------------------------------------


def row_to_record(row: tuple) -> PerformanceRecord:
    """Public (not underscore-prefixed): reused as-is by
    `app/services/dashboard.py` (TRAIN-22) rather than duplicated — same
    row shape `history_repo.list_weighted_performances_for_exercise`/
    `list_weighted_performances_for_exercises` both return.
    """
    (
        weight,
        reps,
        weight_unit,
        completed_at,
        workout_session_id,
        program_id,
        progression_line_id,
    ) = row
    return PerformanceRecord(
        weight=weight,
        reps=reps,
        weight_unit=WeightUnit(weight_unit),
        performed_at=completed_at,
        workout_session_id=workout_session_id,
        program_id=program_id,
        progression_line_id=progression_line_id,
    )


def _display_value(
    *, value: float, comparison_kg: float, unit: WeightUnit, display_unit: WeightUnit
) -> float:
    """The 2dp display-unit figure. Short-circuits to rounding `value` directly
    when no conversion is needed, so the no-conversion case (the common one —
    both values logged in the same unit) never round-trips through kg at all,
    matching the "as-performed `value` is returned exactly as logged, never
    round-tripped through kg" rule for `value` itself.
    """
    if unit == display_unit:
        return round(value, 2)
    return round(from_kg(comparison_kg, display_unit), 2)


def _value_and_comparison_kg(
    effort: Effort, *, kind: PersonalRecordKind
) -> tuple[float, float]:
    """The as-logged figure and its kg comparison value for one PR kind. Shared
    by both `_read` builders below so the `HEAVIEST_WEIGHT` vs.
    `BEST_ESTIMATED_ONE_RM` branch is written once.
    """
    if kind == PersonalRecordKind.HEAVIEST_WEIGHT:
        return effort.weight, effort.weight_kg
    # BEST_ESTIMATED_ONE_RM (and the trend point, which is always an e1RM
    # figure) — effort.one_rm is never None here: it only reaches this branch
    # via best_effort's best_one_rm (already filtered to non-None) or
    # detect_new_records' matching hit.
    return effort.one_rm, effort.one_rm_kg  # type: ignore[return-value]


def personal_record_read(
    *,
    exercise_id: int,
    exercise_name: str,
    kind: PersonalRecordKind,
    effort: Effort,
    display_unit: WeightUnit,
) -> PersonalRecordRead:
    """Public (not underscore-prefixed): reused as-is by
    `app/services/dashboard.py` (TRAIN-22) so a PR hit is built into exactly
    one `PersonalRecordRead` shape everywhere, never a second implementation.
    """
    value, comparison_kg = _value_and_comparison_kg(effort, kind=kind)
    return PersonalRecordRead(
        exercise_id=exercise_id,
        exercise_name=exercise_name,
        kind=kind,
        value=value,
        recorded_unit=effort.weight_unit,
        display_value=_display_value(
            value=value,
            comparison_kg=comparison_kg,
            unit=effort.weight_unit,
            display_unit=display_unit,
        ),
        display_unit=display_unit,
        converted=effort.weight_unit != display_unit,
        reps=effort.reps,
        performed_at=effort.performed_at,
        workout_session_id=effort.workout_session_id,
        program_id=effort.program_id,
        progression_line_id=effort.progression_line_id,
    )


def _trend_point_read(
    *, exercise_id: int, exercise_name: str, effort: Effort, display_unit: WeightUnit
) -> OneRmTrendPointRead:
    value, comparison_kg = _value_and_comparison_kg(
        effort, kind=PersonalRecordKind.BEST_ESTIMATED_ONE_RM
    )
    return OneRmTrendPointRead(
        exercise_id=exercise_id,
        exercise_name=exercise_name,
        value=value,
        recorded_unit=effort.weight_unit,
        display_value=_display_value(
            value=value,
            comparison_kg=comparison_kg,
            unit=effort.weight_unit,
            display_unit=display_unit,
        ),
        display_unit=display_unit,
        converted=effort.weight_unit != display_unit,
        reps=effort.reps,
        performed_at=effort.performed_at,
        workout_session_id=effort.workout_session_id,
        program_id=effort.program_id,
        progression_line_id=effort.progression_line_id,
    )


def list_completed_sessions(
    session: Session,
    *,
    user_id: int,
    program_id: int | None,
    limit: int,
    offset: int,
) -> list[CompletedSessionRead]:
    if program_id is not None:
        # Raises ProgramNotFoundError/ProgramAccessDeniedError if the caller
        # doesn't own it — the route maps both to 404.
        programs_service.get_owned_program(
            session, user_id=user_id, program_id=program_id
        )

    rows = history_repo.list_completed_sessions(
        session, user_id=user_id, program_id=program_id, limit=limit, offset=offset
    )
    return [
        CompletedSessionRead(
            id=workout_session.id,  # type: ignore[arg-type]
            program_id=owning_program_id,
            week_id=workout_session.week_id,
            day_name=workout_session.day_name,
            started_at=workout_session.started_at,
            completed_at=workout_session.completed_at,  # type: ignore[arg-type]
            notes=workout_session.notes,
        )
        for workout_session, owning_program_id in rows
    ]


def get_personal_records(
    session: Session, *, user_id: int, exercise_id: int, display_unit: WeightUnit
) -> list[PersonalRecordRead]:
    """Lifetime bests for `exercise_id`, both kinds — see "Resolved question 1"
    in TRAIN-21's design plan. Empty list if the exercise has no counted
    weighted sets logged yet.
    """
    exercise = exercises_repo.get_visible_exercise(
        session, user_id=user_id, exercise_id=exercise_id
    )
    if exercise is None:
        raise ExerciseNotFoundError(exercise_id)

    rows = history_repo.list_weighted_performances_for_exercise(
        session, user_id=user_id, exercise_id=exercise_id
    )
    best = best_effort([row_to_record(row) for row in rows])
    if best is None:
        return []

    results: list[PersonalRecordRead] = []
    if best.best_weight is not None:
        results.append(
            personal_record_read(
                exercise_id=exercise_id,
                exercise_name=exercise.name,
                kind=PersonalRecordKind.HEAVIEST_WEIGHT,
                effort=best.best_weight,
                display_unit=display_unit,
            )
        )
    if best.best_one_rm is not None:
        results.append(
            personal_record_read(
                exercise_id=exercise_id,
                exercise_name=exercise.name,
                kind=PersonalRecordKind.BEST_ESTIMATED_ONE_RM,
                effort=best.best_one_rm,
                display_unit=display_unit,
            )
        )
    return results


def get_session_personal_records(
    session: Session, *, user_id: int, workout_session_id: int, display_unit: WeightUnit
) -> list[PersonalRecordRead]:
    """PRs set *in* `workout_session_id` — the "at session completion" moment —
    for every exercise trained in it. An incomplete session (never completed,
    so nothing could have been finalized yet) reports no PRs.
    """
    workout_session = workout_sessions_service.get_owned_workout_session(
        session, user_id=user_id, workout_session_id=workout_session_id
    )
    if workout_session.completed_at is None:
        return []

    prescriptions = exercise_prescriptions_repo.list_exercise_prescriptions_for_session(
        session, workout_session_id
    )
    # `.exercise` still lazy-loads once per distinct exercise (no eager
    # loading configured on `list_exercise_prescriptions_for_session`) — this
    # doesn't remove that query. What it removes is the redundant *visibility*
    # check `get_visible_exercise` does on top of a plain PK lookup: these
    # exercises already belong to prescriptions on the caller's own session
    # (ownership already verified above via `get_owned_workout_session`), and
    # `exercise_id` is a NOT NULL FK, so there's nothing left for
    # `get_visible_exercise` to usefully reject here.
    exercise_name_by_id = {p.exercise_id: p.exercise.name for p in prescriptions}
    exercise_ids = sorted(exercise_name_by_id)

    results: list[PersonalRecordRead] = []
    for exercise_id in exercise_ids:
        exercise_name = exercise_name_by_id[exercise_id]

        rows = history_repo.list_weighted_performances_for_exercise(
            session, user_id=user_id, exercise_id=exercise_id
        )
        records = [row_to_record(row) for row in rows]
        prior_records = [
            r for r in records if r.performed_at < workout_session.completed_at
        ]
        session_records = [
            r for r in records if r.workout_session_id == workout_session_id
        ]

        hits = detect_new_records(
            best_effort(session_records), best_effort(prior_records)
        )
        for hit in hits:
            results.append(
                personal_record_read(
                    exercise_id=exercise_id,
                    exercise_name=exercise_name,
                    kind=hit.kind,
                    effort=hit.effort,
                    display_unit=display_unit,
                )
            )
    return results


def get_one_rm_trend(
    session: Session,
    *,
    user_id: int,
    exercise_id: int,
    program_id: int | None,
    limit: int,
    offset: int,
    display_unit: WeightUnit,
) -> list[OneRmTrendPointRead]:
    """One point per completed session — that session's best e1RM for the
    exercise — newest first, across all of the user's programs and
    progression lines unless narrowed by `program_id`. See "Resolved question
    3" in TRAIN-21's design plan.
    """
    exercise = exercises_repo.get_visible_exercise(
        session, user_id=user_id, exercise_id=exercise_id
    )
    if exercise is None:
        raise ExerciseNotFoundError(exercise_id)
    if program_id is not None:
        programs_service.get_owned_program(
            session, user_id=user_id, program_id=program_id
        )

    rows = history_repo.list_weighted_performances_for_exercise(
        session, user_id=user_id, exercise_id=exercise_id
    )
    records = [row_to_record(row) for row in rows]
    if program_id is not None:
        records = [r for r in records if r.program_id == program_id]

    by_session: dict[int, list[PerformanceRecord]] = defaultdict(list)
    for record in records:
        by_session[record.workout_session_id].append(record)

    points: list[Effort] = []
    for session_records in by_session.values():
        best = best_effort(session_records)
        if best is not None and best.best_one_rm is not None:
            points.append(best.best_one_rm)
    points.sort(key=lambda e: e.performed_at, reverse=True)

    page = points[offset : offset + limit]
    return [
        _trend_point_read(
            exercise_id=exercise_id,
            exercise_name=exercise.name,
            effort=effort,
            display_unit=display_unit,
        )
        for effort in page
    ]

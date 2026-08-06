"""Progression engine: compares planned (`ExercisePrescription`) vs actual
(`ExercisePerformance`) and produces an advisory next-session weight recommendation.
Mutates nothing — see TRAIN-20.

Two layers, deliberately split:

- `calculate_recommendation` (+ `evaluate_attempt`) are **pure functions** — no
  `Session`, no I/O — so CLAUDE.md's "unit tests in tests/services/, no DB, don't mock
  the engine" is directly achievable. Most of TRAIN-20's tests hit these directly.
- `resolve_settings` and `get_recommendation_for_prescription` do the DB-touching
  orchestration: ownership check, config resolution, history fetch, then delegate to
  the pure function.
"""

from dataclasses import dataclass
from typing import Literal

from sqlmodel import Session

from app.models.enums import ProgressionType, SetCompletionState, WeightUnit
from app.models.exercise_performance import ExercisePerformance
from app.models.exercise_prescription import ExercisePrescription
from app.models.program import Program
from app.repositories import exercise_prescriptions as exercise_prescriptions_repo
from app.schemas.progression import (
    DeloadSettings,
    ProgressionSettings,
    RecommendationRead,
)
from app.services import exercise_prescriptions as exercise_prescriptions_service

# Re-exported so callers (routes, tests) don't have to reach into
# exercise_prescriptions_service directly to catch these — same pattern
# api/exercise_performances.py already uses for these two exceptions.
ExercisePrescriptionNotFoundError = (
    exercise_prescriptions_service.ExercisePrescriptionNotFoundError
)
ExercisePrescriptionAccessDeniedError = (
    exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError
)

Action = Literal[
    "increase", "hold", "deload", "manual", "no_data", "needs_configuration"
]

# Built-in defaults — used only when neither the prescription nor the program set a
# given key. Every one of these is overridable via `progression_params`.
_DEFAULT_DELOAD_ENABLED = True
_DEFAULT_DELOAD_FAILURE_THRESHOLD = 3
_DEFAULT_DELOAD_PERCENTAGE = 0.10
_DEFAULT_ROUNDING_INCREMENT_KG = 2.5
_DEFAULT_ROUNDING_INCREMENT_LB = 5.0

# Extra rows fetched beyond the resolved failure_threshold, so a weight-decrease reset
# boundary just past the threshold is still visible to the consecutive-failure walk.
_HISTORY_BUFFER = 5


@dataclass(frozen=True)
class AttemptOutcome:
    """One prior attempt's outcome. Callers order these newest-first."""

    weight: float | None
    successful: bool


@dataclass(frozen=True)
class RecommendationResult:
    recommended_weight: float | None
    current_weight: float | None
    action: Action
    progression_type: ProgressionType
    consecutive_failures: int
    reason: str


def _round_to_increment(weight: float, increment: float) -> float:
    if increment <= 0:
        return weight
    return round(weight / increment) * increment


def _representative_weight(performances: list[ExercisePerformance]) -> float | None:
    """The weight this attempt was actually performed at: the lowest-set-number
    logged weight (working sets are typically uniform; the first set is the least
    fatigue-affected reference point), falling back to any other logged set's weight.
    """
    for performance in sorted(performances, key=lambda p: p.set_number):
        if performance.actual_weight is not None:
            return performance.actual_weight
    return None


def evaluate_attempt(
    *, target_sets: int, target_reps: int, performances: list[ExercisePerformance]
) -> AttemptOutcome:
    """Strict success rule: all `target_sets` sets logged, every set `completed`,
    every set's `actual_reps >= target_reps`. Anything less — including `skipped`
    sets, or fewer sets logged than prescribed — fails. Pure: no DB, no I/O.
    """
    successful = (
        len(performances) >= target_sets
        and all(
            p.completion_state == SetCompletionState.COMPLETED for p in performances
        )
        and all(p.actual_reps >= target_reps for p in performances)
    )
    return AttemptOutcome(
        weight=_representative_weight(performances), successful=successful
    )


def _count_consecutive_failures(prior_attempts: list[AttemptOutcome]) -> int:
    """Walk newest-first, counting failures back to either the last success or the
    last observed weight decrease, whichever comes first.

    The weight-decrease condition stands in for "reset the failure counter": a deload
    the athlete actually took shows up as a lower logged weight on the next attempt.
    Without this, a deload actually taken would be re-recommended forever.
    """
    count = 0
    newer_weight: float | None = None
    for attempt in prior_attempts:
        if attempt.successful:
            break
        if (
            newer_weight is not None
            and attempt.weight is not None
            and attempt.weight > newer_weight
        ):
            # Weight dropped going from this (older) attempt to the next-newer one —
            # a deload boundary. Stop before crossing it.
            break
        count += 1
        newer_weight = attempt.weight
    return count


def calculate_recommendation(
    *,
    target_weight: float | None,
    prior_attempts: list[AttemptOutcome],
    settings: ProgressionSettings,
) -> RecommendationResult:
    """Pure: no `Session`, no I/O. `prior_attempts` must be ordered newest-first."""
    if not prior_attempts:
        return RecommendationResult(
            recommended_weight=target_weight,
            current_weight=target_weight,
            action="no_data",
            progression_type=settings.progression_type,
            consecutive_failures=0,
            reason="No completed attempts logged yet for this exercise.",
        )

    current_weight = prior_attempts[0].weight
    if current_weight is None:
        current_weight = target_weight

    consecutive_failures = _count_consecutive_failures(prior_attempts)

    if (
        settings.deload.enabled
        and consecutive_failures >= settings.deload.failure_threshold
    ):
        if current_weight is None:
            return RecommendationResult(
                recommended_weight=None,
                current_weight=None,
                action="needs_configuration",
                progression_type=settings.progression_type,
                consecutive_failures=consecutive_failures,
                reason="No logged weight available to base a deload on.",
            )
        recommended = _round_to_increment(
            current_weight * (1 - settings.deload.percentage),
            settings.rounding_increment,
        )
        return RecommendationResult(
            recommended_weight=recommended,
            current_weight=current_weight,
            action="deload",
            progression_type=settings.progression_type,
            consecutive_failures=consecutive_failures,
            reason=(
                f"{consecutive_failures} consecutive failures reached the "
                f"{settings.deload.failure_threshold}-failure deload threshold."
            ),
        )

    if not prior_attempts[0].successful:
        return RecommendationResult(
            recommended_weight=current_weight,
            current_weight=current_weight,
            action="hold",
            progression_type=settings.progression_type,
            consecutive_failures=consecutive_failures,
            reason="Last attempt fell short of target reps — hold the same weight.",
        )

    if settings.progression_type == ProgressionType.MANUAL:
        return RecommendationResult(
            recommended_weight=current_weight,
            current_weight=current_weight,
            action="manual",
            progression_type=settings.progression_type,
            consecutive_failures=consecutive_failures,
            reason="Manual progression — set the next weight yourself.",
        )

    if settings.progression_type == ProgressionType.FIXED_INCREMENT:
        if settings.increment is None or current_weight is None:
            return RecommendationResult(
                recommended_weight=None,
                current_weight=current_weight,
                action="needs_configuration",
                progression_type=settings.progression_type,
                consecutive_failures=consecutive_failures,
                reason="Fixed-increment progression is missing its `increment` value.",
            )
        recommended = _round_to_increment(
            current_weight + settings.increment, settings.rounding_increment
        )
        return RecommendationResult(
            recommended_weight=recommended,
            current_weight=current_weight,
            action="increase",
            progression_type=settings.progression_type,
            consecutive_failures=consecutive_failures,
            reason="Last attempt succeeded — increase by the fixed increment.",
        )

    if settings.progression_type == ProgressionType.PERCENTAGE:
        if settings.percentage is None or current_weight is None:
            return RecommendationResult(
                recommended_weight=None,
                current_weight=current_weight,
                action="needs_configuration",
                progression_type=settings.progression_type,
                consecutive_failures=consecutive_failures,
                reason="Percentage-based progression is missing its `percentage` value.",
            )
        recommended = _round_to_increment(
            current_weight * (1 + settings.percentage), settings.rounding_increment
        )
        return RecommendationResult(
            recommended_weight=recommended,
            current_weight=current_weight,
            action="increase",
            progression_type=settings.progression_type,
            consecutive_failures=consecutive_failures,
            reason="Last attempt succeeded — increase by the configured percentage.",
        )

    # Unreachable given ProgressionType's members today, but keeps this exhaustive
    # rather than silently falling through if the enum grows.
    return RecommendationResult(
        recommended_weight=current_weight,
        current_weight=current_weight,
        action="needs_configuration",
        progression_type=settings.progression_type,
        consecutive_failures=consecutive_failures,
        reason="Unrecognized progression type.",
    )


def _extract_number(
    source: dict | None,
    key: str,
    *,
    minimum: float | None = None,
    exclusive_min: float | None = None,
    exclusive_max: float | None = None,
) -> float | None:
    """Defensive extraction: returns None for anything missing, wrong-typed, or
    out of range rather than raising. This is what keeps `resolve_settings` from
    ever 500ing on a malformed legacy row.
    """
    if not isinstance(source, dict):
        return None
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if minimum is not None and value < minimum:
        return None
    if exclusive_min is not None and value <= exclusive_min:
        return None
    if exclusive_max is not None and value >= exclusive_max:
        return None
    return value


def _extract_bool(source: dict | None, key: str) -> bool | None:
    if not isinstance(source, dict):
        return None
    value = source.get(key)
    return value if isinstance(value, bool) else None


def _extract_int(
    source: dict | None, key: str, *, minimum: int | None = None
) -> int | None:
    if not isinstance(source, dict):
        return None
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if minimum is not None and value < minimum:
        return None
    return value


def _resolve_number(
    prescription_params: dict, program_params: dict, key: str, **bounds: float
) -> float | None:
    value = _extract_number(prescription_params, key, **bounds)
    if value is not None:
        return value
    return _extract_number(program_params, key, **bounds)


def _resolve_deload(prescription_params: dict, program_params: dict) -> DeloadSettings:
    prescription_deload = prescription_params.get("deload")
    program_deload = program_params.get("deload")

    enabled = _extract_bool(prescription_deload, "enabled")
    if enabled is None:
        enabled = _extract_bool(program_deload, "enabled")
    if enabled is None:
        enabled = _DEFAULT_DELOAD_ENABLED

    failure_threshold = _extract_int(
        prescription_deload, "failure_threshold", minimum=1
    )
    if failure_threshold is None:
        failure_threshold = _extract_int(program_deload, "failure_threshold", minimum=1)
    if failure_threshold is None:
        failure_threshold = _DEFAULT_DELOAD_FAILURE_THRESHOLD

    percentage = _extract_number(
        prescription_deload, "percentage", exclusive_min=0, exclusive_max=1
    )
    if percentage is None:
        percentage = _extract_number(
            program_deload, "percentage", exclusive_min=0, exclusive_max=1
        )
    if percentage is None:
        percentage = _DEFAULT_DELOAD_PERCENTAGE

    return DeloadSettings(
        enabled=enabled, failure_threshold=failure_threshold, percentage=percentage
    )


def resolve_settings(
    *, prescription: ExercisePrescription, program: Program
) -> ProgressionSettings:
    """Merge prescription `progression_params` over program `default_progression_params`
    over built-in defaults, **per key** — never wholesale, so an athlete can override
    just `increment` for one lift without restating the whole deload block.

    Tolerant by construction: every value is extracted defensively via `_extract_*`
    before this ever builds a `ProgressionSettings`, so a malformed stored row can
    never raise here — it just falls back to the next level down.
    """
    prescription_params = prescription.progression_params or {}
    program_params = program.default_progression_params or {}

    progression_type = (
        prescription.progression_type
        or program.default_progression_type
        or ProgressionType.MANUAL
    )

    increment = _resolve_number(
        prescription_params, program_params, "increment", minimum=0
    )
    percentage = _resolve_number(
        prescription_params,
        program_params,
        "percentage",
        exclusive_min=0,
        exclusive_max=1,
    )

    default_rounding = (
        _DEFAULT_ROUNDING_INCREMENT_KG
        if program.weight_unit == WeightUnit.KG
        else _DEFAULT_ROUNDING_INCREMENT_LB
    )
    rounding_increment = (
        _resolve_number(
            prescription_params, program_params, "rounding_increment", exclusive_min=0
        )
        or default_rounding
    )

    deload = _resolve_deload(prescription_params, program_params)

    return ProgressionSettings(
        progression_type=progression_type,
        increment=increment,
        percentage=percentage,
        rounding_increment=rounding_increment,
        deload=deload,
    )


def get_recommendation_for_prescription(
    session: Session, *, user_id: int, prescription_id: int
) -> RecommendationRead:
    """Ownership check, history fetch, settings resolution, then delegates to the
    pure `calculate_recommendation`. Read-only — mutates nothing.
    """
    prescription = exercise_prescriptions_service.get_owned_exercise_prescription(
        session, user_id=user_id, prescription_id=prescription_id
    )
    # Traversed via the already-loaded relationship chain (prescription ->
    # workout_session -> week -> program), same join chain the ownership check just
    # used underneath — no separate query needed.
    program = prescription.workout_session.week.program

    settings = resolve_settings(prescription=prescription, program=program)

    history_limit = settings.deload.failure_threshold + _HISTORY_BUFFER
    prior_rows = exercise_prescriptions_repo.list_prior_attempts(
        session,
        program_id=program.id,
        exercise_id=prescription.exercise_id,
        limit=history_limit,
    )
    prior_attempts = [
        evaluate_attempt(
            target_sets=prior_prescription.target_sets,
            target_reps=prior_prescription.target_reps,
            performances=performances,
        )
        for prior_prescription, performances in prior_rows
    ]

    result = calculate_recommendation(
        target_weight=prescription.target_weight,
        prior_attempts=prior_attempts,
        settings=settings,
    )

    return RecommendationRead(
        recommended_weight=result.recommended_weight,
        current_weight=result.current_weight,
        action=result.action,
        progression_type=result.progression_type,
        consecutive_failures=result.consecutive_failures,
        reason=result.reason,
        settings_used=settings,
    )

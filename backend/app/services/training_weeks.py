"""TrainingWeek CRUD business logic: ownership enforcement and week-number
assignment/collision handling live here, not in the routes.

Routes only translate these exceptions into HTTP responses.
"""

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models.training_week import TrainingWeek
from app.repositories import exercise_prescriptions as exercise_prescriptions_repo
from app.repositories import training_weeks as training_weeks_repo
from app.repositories import workout_sessions as workout_sessions_repo
from app.schemas.training_weeks import (
    TrainingWeekCreate,
    TrainingWeekGenerateRequest,
    TrainingWeekUpdate,
)
from app.services import programs as programs_service
from app.services import progression as progression_service

# Recommendation actions with no confident number to suggest — for these, the new
# prescription's target_weight falls back to a verbatim copy of the source's
# target_weight rather than the engine's (non-actionable) recommended_weight.
_NO_CONFIDENT_RECOMMENDATION_ACTIONS = {"manual", "no_data", "needs_configuration"}


class TrainingWeekNotFoundError(Exception):
    """No training week exists with that id."""


class TrainingWeekAccessDeniedError(Exception):
    """The training week exists but its program belongs to a different user."""


class DuplicateWeekNumberError(Exception):
    """That week_number is already taken within this program."""


class InvalidTrainingWeekUpdateError(Exception):
    """A required (non-nullable) field was explicitly set to null."""


# Columns that are NOT NULL at the DB level — an explicit `null` for one of
# these in a partial update must be rejected as a 422, not left to reach the
# DB and raise an IntegrityError (which would either 500 or, worse, get
# mis-mapped onto DuplicateWeekNumberError below).
_NON_NULLABLE_UPDATE_FIELDS = {"week_number"}


def _reject_null_updates(updates: dict) -> None:
    nulled = [
        field
        for field in _NON_NULLABLE_UPDATE_FIELDS
        if field in updates and updates[field] is None
    ]
    if nulled:
        raise InvalidTrainingWeekUpdateError(
            f"{', '.join(sorted(nulled))} cannot be null"
        )


def get_owned_training_week(
    session: Session, *, user_id: int, week_id: int
) -> TrainingWeek:
    """Fetch a training week whose program the caller owns, or raise.

    Not-found and access-denied are kept as distinct exceptions for callers that
    care, but the API layer maps both to 404 so a non-owner can't learn a week id
    exists.
    """
    result = training_weeks_repo.get_training_week_with_owner(session, week_id)
    if result is None:
        raise TrainingWeekNotFoundError(week_id)
    week, owner_user_id = result
    if owner_user_id != user_id:
        raise TrainingWeekAccessDeniedError(week_id)
    return week


def list_training_weeks(
    session: Session, *, user_id: int, program_id: int
) -> list[TrainingWeek]:
    # Raises ProgramNotFoundError/ProgramAccessDeniedError if the caller doesn't
    # own the program — the route maps those to 404 too.
    programs_service.get_owned_program(session, user_id=user_id, program_id=program_id)
    return training_weeks_repo.list_training_weeks_for_program(session, program_id)


def create_training_week_for_program(
    session: Session, *, user_id: int, program_id: int, payload: TrainingWeekCreate
) -> TrainingWeek:
    programs_service.get_owned_program(session, user_id=user_id, program_id=program_id)

    auto_assigned = payload.week_number is None
    week_number = payload.week_number
    if week_number is None:
        max_week_number = training_weeks_repo.get_max_week_number(session, program_id)
        week_number = 1 if max_week_number is None else max_week_number + 1
    else:
        existing = training_weeks_repo.find_by_week_number(
            session, program_id=program_id, week_number=week_number
        )
        if existing is not None:
            raise DuplicateWeekNumberError(week_number)

    # Belt-and-braces guarantee against the upfront check's check-then-act race,
    # same pattern as exercises_service.create_custom_exercise. When the number
    # was auto-assigned (client sent none), a lost race is retried once against
    # a freshly recomputed max rather than surfaced as a 409 the client never
    # asked for — the client didn't propose a number, so it shouldn't see a
    # "that number is taken" error.
    for attempt in range(2):
        try:
            return training_weeks_repo.create_training_week(
                session,
                program_id=program_id,
                week_number=week_number,
                name=payload.name,
            )
        except IntegrityError as exc:
            # week_number is always a concrete int by this point (either
            # explicit or auto-assigned above), so this is the week_number
            # unique constraint by construction — no other NOT NULL/FK
            # violation is expected here.
            session.rollback()
            if auto_assigned and attempt == 0:
                max_week_number = training_weeks_repo.get_max_week_number(
                    session, program_id
                )
                week_number = 1 if max_week_number is None else max_week_number + 1
                continue
            raise DuplicateWeekNumberError(week_number) from exc
    raise AssertionError("unreachable")  # pragma: no cover


def update_training_week(
    session: Session, *, user_id: int, week_id: int, payload: TrainingWeekUpdate
) -> TrainingWeek:
    week = get_owned_training_week(session, user_id=user_id, week_id=week_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return week
    _reject_null_updates(updates)

    new_week_number = updates.get("week_number")
    if new_week_number is not None and new_week_number != week.week_number:
        existing = training_weeks_repo.find_by_week_number(
            session, program_id=week.program_id, week_number=new_week_number
        )
        if existing is not None and existing.id != week.id:
            raise DuplicateWeekNumberError(new_week_number)

    try:
        return training_weeks_repo.update_training_week(session, week, **updates)
    except IntegrityError as exc:
        session.rollback()
        # Only attribute this to the week_number unique constraint when the
        # update actually touched week_number — an update to unrelated fields
        # (e.g. `name`) that somehow raises an IntegrityError is a genuine,
        # unexpected DB error and shouldn't be mis-reported as a 409 about a
        # week number the request never mentioned.
        if new_week_number is None:
            raise
        raise DuplicateWeekNumberError(new_week_number) from exc


def delete_training_week(session: Session, *, user_id: int, week_id: int) -> None:
    week = get_owned_training_week(session, user_id=user_id, week_id=week_id)
    training_weeks_repo.delete_training_week(session, week)


def _resolve_target_weight(
    *,
    source_target_weight: float | None,
    recommendation: progression_service.RecommendationResult,
) -> float | None:
    """Per the TRAIN-26 addendum, plus one defensive guard: use the engine's
    `recommended_weight` unless the action carries no confident number
    (`manual`/`no_data`/`needs_configuration`) or `recommended_weight` is itself
    `None` — `action="hold"` returns `current_weight`, which is legitimately `None`
    for bodyweight work, and without this guard that would blank out a prescribed
    weight instead of falling back to the source's.
    """
    if (
        recommendation.action in _NO_CONFIDENT_RECOMMENDATION_ACTIONS
        or recommendation.recommended_weight is None
    ):
        return source_target_weight
    return recommendation.recommended_weight


def generate_next_training_week(
    session: Session,
    *,
    user_id: int,
    week_id: int,
    payload: TrainingWeekGenerateRequest,
) -> TrainingWeek:
    """Copy `week_id`'s WorkoutSession/ExercisePrescription structure into a new,
    appended week of the same program — each prescription's `progression_line_id`
    carried forward unchanged, each `target_weight` pre-filled from the progression
    engine rather than copied. No `ExercisePerformance` rows are ever copied.

    Read phase (ownership, source tree, recommendations) happens entirely before the
    single write transaction delegated to `training_weeks_repo.create_week_from_source`
    — the recommendation computation is read-only, so it's safe to run upfront.
    """
    source_week = get_owned_training_week(session, user_id=user_id, week_id=week_id)
    program = programs_service.get_owned_program(
        session, user_id=user_id, program_id=source_week.program_id
    )

    source_sessions = workout_sessions_repo.list_workout_sessions_for_week(
        session, source_week.id
    )
    source_session_ids = [workout_session.id for workout_session in source_sessions]
    source_prescriptions = (
        exercise_prescriptions_repo.list_exercise_prescriptions_for_sessions(
            session, source_session_ids
        )
    )

    recommendations = progression_service.get_recommendations_for_prescriptions(
        session, program=program, prescriptions=source_prescriptions
    )
    target_weight_by_prescription_id = {
        prescription.id: _resolve_target_weight(
            source_target_weight=prescription.target_weight,
            recommendation=recommendations[prescription.id],
        )
        for prescription in source_prescriptions
    }

    max_week_number = training_weeks_repo.get_max_week_number(session, program.id)
    week_number = 1 if max_week_number is None else max_week_number + 1

    try:
        return training_weeks_repo.create_week_from_source(
            session,
            program_id=program.id,
            week_number=week_number,
            name=payload.name,
            source_sessions=source_sessions,
            source_prescriptions=source_prescriptions,
            target_weight_by_prescription_id=target_weight_by_prescription_id,
        )
    except IntegrityError as exc:
        # The uq_training_week_program_number race — a double-tap. No retry (see
        # design plan): silently retrying would create a second near-identical
        # week, so this surfaces as a 409 instead.
        #
        # Unlike update_training_week, this attributes *any* IntegrityError here to
        # the week_number constraint without checking which column it names. That's
        # deliberate, not an oversight: every row create_week_from_source writes is
        # built from an already-valid source tree (FK values copied verbatim from
        # rows that satisfied the same constraints when the source week was
        # created), so week_number is the only constraint this call can plausibly
        # violate — same reasoning create_training_week_for_program's retry loop
        # already relies on above.
        session.rollback()
        raise DuplicateWeekNumberError(week_number) from exc

"""ExercisePrescription CRUD business logic: ownership enforcement, order_index
assignment, and exercise-visibility checks live here, not in the routes.

Routes only translate these exceptions into HTTP responses.
"""

from sqlmodel import Session

from app.models.exercise_prescription import ExercisePrescription
from app.models.progression_line import ProgressionLine
from app.repositories import exercise_prescriptions as exercise_prescriptions_repo
from app.repositories import exercises as exercises_repo
from app.repositories import progression_lines as progression_lines_repo
from app.schemas.exercise_prescriptions import (
    ExercisePrescriptionCreate,
    ExercisePrescriptionUpdate,
)
from app.services import workout_sessions as workout_sessions_service


class ExercisePrescriptionNotFoundError(Exception):
    """No exercise prescription exists with that id."""


class ExercisePrescriptionAccessDeniedError(Exception):
    """The prescription exists but its program belongs to a different user."""


class ExerciseNotVisibleError(Exception):
    """The referenced exercise doesn't exist or isn't visible to this user."""


class InvalidExercisePrescriptionUpdateError(Exception):
    """A required (non-nullable) field was explicitly set to null."""


class InvalidProgressionLineReferenceError(Exception):
    """`progression_line_id` doesn't exist, or belongs to a different program or
    exercise than this prescription's.
    """


# Columns that are NOT NULL at the DB level — an explicit `null` for one of
# these in a partial update must be rejected as a 422, not left to reach the
# DB and raise an uncaught IntegrityError (500), or in exercise_id's case,
# fall through to get_visible_exercise and raise a misleading "Exercise not
# found" 404 for a request that never named an exercise at all.
_NON_NULLABLE_UPDATE_FIELDS = {
    "exercise_id",
    "order_index",
    "target_sets",
    "target_reps",
}


def _reject_null_updates(updates: dict) -> None:
    nulled = [
        field
        for field in _NON_NULLABLE_UPDATE_FIELDS
        if field in updates and updates[field] is None
    ]
    if nulled:
        raise InvalidExercisePrescriptionUpdateError(
            f"{', '.join(sorted(nulled))} cannot be null"
        )


def _find_or_create_default_progression_line(
    session: Session, *, program_id: int, exercise_id: int
) -> ProgressionLine:
    """The zero-configuration path: neither `progression_line_id` nor
    `start_new_progression_line` set on create. Find-or-create, not upsert — the
    partial unique index (`is_default` per program+exercise) is the real guarantee.
    A concurrent double-create surfaces as an `IntegrityError` (a 500 via the
    existing global handler) rather than two competing default lines silently
    splitting an athlete's history. Given a solo-dev, single-user-per-program
    workload, that trade is fine as-is — no retry/upsert machinery needed.
    """
    line = progression_lines_repo.get_default_progression_line(
        session, program_id=program_id, exercise_id=exercise_id
    )
    if line is not None:
        return line
    return progression_lines_repo.create_progression_line(
        session,
        program_id=program_id,
        exercise_id=exercise_id,
        is_default=True,
        label=None,
    )


def resolve_progression_line_for_new_prescription(
    session: Session,
    *,
    program_id: int,
    exercise_id: int,
    progression_line_id: int | None,
    start_new_progression_line_label: str | None,
    starting_new_line: bool,
) -> ProgressionLine:
    """Resolves which line a new prescription attaches to. Called after ownership
    and exercise-visibility checks so a failed validation can never leave an orphan
    line row.

    Three branches, matching the create payload's three progression-line shapes
    (mutual exclusivity of the two optional fields is enforced by the schema):

    1. Neither set -> find-or-create the (program, exercise) default line.
    2. `progression_line_id` set -> must belong to this program and exercise, or
       raise (-> 422). This is also what prevents another user's line id from
       being attached (ownership of the *program* is already established by the
       caller before this runs).
    3. `start_new_progression_line` set -> create a new, explicit non-default
       line. Does not also materialize the default line: a user whose very first
       use of an exercise is an explicit split simply has no default line yet.
    """
    if progression_line_id is not None:
        line = progression_lines_repo.get_progression_line(session, progression_line_id)
        if (
            line is None
            or line.program_id != program_id
            or line.exercise_id != exercise_id
        ):
            raise InvalidProgressionLineReferenceError(progression_line_id)
        return line

    if starting_new_line:
        return progression_lines_repo.create_progression_line(
            session,
            program_id=program_id,
            exercise_id=exercise_id,
            is_default=False,
            label=start_new_progression_line_label,
        )

    return _find_or_create_default_progression_line(
        session, program_id=program_id, exercise_id=exercise_id
    )


def get_owned_exercise_prescription(
    session: Session, *, user_id: int, prescription_id: int
) -> ExercisePrescription:
    """Fetch a prescription whose program the caller owns, or raise.

    Not-found and access-denied are kept as distinct exceptions for callers that
    care, but the API layer maps both to 404 so a non-owner can't learn a
    prescription id exists.
    """
    result = exercise_prescriptions_repo.get_exercise_prescription_with_owner(
        session, prescription_id
    )
    if result is None:
        raise ExercisePrescriptionNotFoundError(prescription_id)
    prescription, owner_user_id = result
    if owner_user_id != user_id:
        raise ExercisePrescriptionAccessDeniedError(prescription_id)
    return prescription


def list_exercise_prescriptions(
    session: Session, *, user_id: int, workout_session_id: int
) -> list[ExercisePrescription]:
    # Raises WorkoutSessionNotFoundError/WorkoutSessionAccessDeniedError if the
    # caller doesn't own the parent session — the route maps those to 404 too.
    workout_sessions_service.get_owned_workout_session(
        session, user_id=user_id, workout_session_id=workout_session_id
    )
    return exercise_prescriptions_repo.list_exercise_prescriptions_for_session(
        session, workout_session_id
    )


def create_exercise_prescription_for_session(
    session: Session,
    *,
    user_id: int,
    workout_session_id: int,
    payload: ExercisePrescriptionCreate,
) -> ExercisePrescription:
    workout_session = workout_sessions_service.get_owned_workout_session(
        session, user_id=user_id, workout_session_id=workout_session_id
    )

    exercise = exercises_repo.get_visible_exercise(
        session, user_id=user_id, exercise_id=payload.exercise_id
    )
    if exercise is None:
        raise ExerciseNotVisibleError(payload.exercise_id)

    program_id = workout_session.week.program_id
    progression_line = resolve_progression_line_for_new_prescription(
        session,
        program_id=program_id,
        exercise_id=payload.exercise_id,
        progression_line_id=payload.progression_line_id,
        start_new_progression_line_label=(
            payload.start_new_progression_line.label
            if payload.start_new_progression_line is not None
            else None
        ),
        starting_new_line=payload.start_new_progression_line is not None,
    )

    order_index = payload.order_index
    if order_index is None:
        max_order_index = exercise_prescriptions_repo.get_max_order_index(
            session, workout_session_id
        )
        order_index = 0 if max_order_index is None else max_order_index + 1

    return exercise_prescriptions_repo.create_exercise_prescription(
        session,
        workout_session_id=workout_session_id,
        exercise_id=payload.exercise_id,
        progression_line_id=progression_line.id,
        order_index=order_index,
        target_sets=payload.target_sets,
        target_reps=payload.target_reps,
        target_weight=payload.target_weight,
        target_rpe=payload.target_rpe,
        progression_type=payload.progression_type,
        # SQLModel won't serialize a ProgressionParams instance into the JSONB
        # column — dump it to a plain dict first.
        progression_params=(
            payload.progression_params.model_dump(exclude_unset=True)
            if payload.progression_params is not None
            else None
        ),
        notes=payload.notes,
    )


def update_exercise_prescription(
    session: Session,
    *,
    user_id: int,
    prescription_id: int,
    payload: ExercisePrescriptionUpdate,
) -> ExercisePrescription:
    prescription = get_owned_exercise_prescription(
        session, user_id=user_id, prescription_id=prescription_id
    )
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return prescription
    _reject_null_updates(updates)

    new_progression_line_id: int | None = None
    if "exercise_id" in updates:
        new_exercise_id = updates["exercise_id"]
        exercise = exercises_repo.get_visible_exercise(
            session, user_id=user_id, exercise_id=new_exercise_id
        )
        if exercise is None:
            raise ExerciseNotVisibleError(new_exercise_id)

        # Every prescription has a line (NOT NULL FK, RESTRICT — it can never
        # point at a deleted or missing row, so `current_line` is guaranteed
        # non-None here), so an exercise change always invalidates the current
        # one: it belongs to the old exercise. Not a blanket 422 (that would
        # regress the pre-line behavior of "fixing a mis-picked exercise just
        # works"):
        current_line = progression_lines_repo.get_progression_line(
            session, prescription.progression_line_id
        )
        if current_line.is_default:  # type: ignore[union-attr]
            # Default line -> silently re-resolve to the new exercise's default
            # line (find-or-create). Behavior identical to today. Resolved here,
            # *before* the write below, so both the new exercise_id and the new
            # progression_line_id land in the same commit.
            program_id = prescription.workout_session.week.program_id
            new_line = _find_or_create_default_progression_line(
                session, program_id=program_id, exercise_id=new_exercise_id
            )
            new_progression_line_id = new_line.id
        else:
            # Explicit non-default line -> the user deliberately created that
            # line for that exercise; silently moving it across exercises would
            # corrupt exactly what progression lines protect.
            raise InvalidExercisePrescriptionUpdateError(
                "exercise_id cannot be changed on a prescription that belongs to "
                "an explicit (non-default) progression line"
            )

    if new_progression_line_id is not None:
        # Single commit: exercise_id and progression_line_id must land together,
        # never as two separately-committed writes — see
        # update_exercise_prescription_with_progression_line's docstring.
        return exercise_prescriptions_repo.update_exercise_prescription_with_progression_line(
            session,
            prescription,
            progression_line_id=new_progression_line_id,
            **updates,
        )
    return exercise_prescriptions_repo.update_exercise_prescription(
        session, prescription, **updates
    )


def delete_exercise_prescription(
    session: Session, *, user_id: int, prescription_id: int
) -> None:
    prescription = get_owned_exercise_prescription(
        session, user_id=user_id, prescription_id=prescription_id
    )
    exercise_prescriptions_repo.delete_exercise_prescription(session, prescription)

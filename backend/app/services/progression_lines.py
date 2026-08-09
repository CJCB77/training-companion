"""ProgressionLine business logic: ownership enforcement lives here, not in the
routes. See CLAUDE.md's "Progression Lines" for the model this implements.

Routes only translate these exceptions into HTTP responses.
"""

from sqlmodel import Session

from app.models.progression_line import ProgressionLine
from app.repositories import progression_lines as progression_lines_repo
from app.schemas.progression_lines import ProgressionLineUpdate
from app.services import programs as programs_service


class ProgressionLineNotFoundError(Exception):
    """No progression line exists with that id."""


class ProgressionLineAccessDeniedError(Exception):
    """The line exists but its program belongs to a different user."""


def get_owned_progression_line(
    session: Session, *, user_id: int, line_id: int
) -> ProgressionLine:
    """Fetch a progression line whose program the caller owns, or raise.

    Not-found and access-denied are kept as distinct exceptions for callers that
    care, but the API layer maps both to 404 so a non-owner can't learn a line id
    exists.
    """
    result = progression_lines_repo.get_progression_line_with_owner(session, line_id)
    if result is None:
        raise ProgressionLineNotFoundError(line_id)
    line, owner_user_id = result
    if owner_user_id != user_id:
        raise ProgressionLineAccessDeniedError(line_id)
    return line


def list_progression_lines(
    session: Session, *, user_id: int, program_id: int, exercise_id: int
) -> list[ProgressionLine]:
    # Raises ProgramNotFoundError/ProgramAccessDeniedError if the caller doesn't
    # own the program — the route maps those to 404 too.
    programs_service.get_owned_program(session, user_id=user_id, program_id=program_id)
    return progression_lines_repo.list_progression_lines(
        session, program_id=program_id, exercise_id=exercise_id
    )


def rename_progression_line(
    session: Session, *, user_id: int, line_id: int, payload: ProgressionLineUpdate
) -> ProgressionLine:
    """Label-only update. Renaming is decorative — it never touches `is_default`
    and never touches any prescription; see CLAUDE.md's "the label is decorative
    only" and the label-immateriality acceptance criterion this is built to satisfy.

    `exclude_unset=True`, matching the partial-update convention every other
    write endpoint here uses (see `exercise_prescriptions_service.
    update_exercise_prescription`): an empty `PATCH {}` body is a no-op rather
    than clearing the label. An explicit `{"label": null}` still clears it —
    that key *is* set, just to `None`.
    """
    line = get_owned_progression_line(session, user_id=user_id, line_id=line_id)
    updates = payload.model_dump(exclude_unset=True)
    if "label" not in updates:
        return line
    return progression_lines_repo.update_progression_line_label(
        session, line, updates["label"]
    )

"""ProgramTemplate business logic: read-only listing plus "generate program from
template". See CLAUDE.md's "Progression Lines" and TRAIN-24's design plan.

Routes only translate these exceptions into HTTP responses.
"""

from sqlmodel import Session

from app.models.program import Program
from app.models.program_template import ProgramTemplate
from app.repositories import exercises as exercises_repo
from app.repositories import program_templates as program_templates_repo
from app.repositories import programs as programs_repo
from app.schemas.program_templates import ProgramGenerateRequest, TemplateStructure


class ProgramTemplateNotFoundError(Exception):
    """No program template exists with that id."""


class TemplateExerciseNotFoundError(Exception):
    """A template's structure references an exercise name that has no matching
    system exercise — a seed-integrity bug, not bad client input (see TRAIN-24's
    design plan: the seed-integrity test is the real defense against this).
    """


def list_templates(session: Session) -> list[ProgramTemplate]:
    return program_templates_repo.list_program_templates(session)


def get_template(session: Session, template_id: int) -> ProgramTemplate:
    template = program_templates_repo.get_program_template(session, template_id)
    if template is None:
        raise ProgramTemplateNotFoundError(template_id)
    return template


def generate_program_from_template(
    session: Session,
    *,
    user_id: int,
    template_id: int,
    payload: ProgramGenerateRequest,
) -> Program:
    """Build a fully independent, caller-owned Program from a template's structure.
    The template row is only ever read here, never written to — see
    `programs_repo.create_program_from_template_structure`'s docstring for why that
    makes template independence true by construction.
    """
    template = get_template(session, template_id)
    structure = TemplateStructure.model_validate(template.structure)

    exercise_names = {
        prescription.exercise_name
        for week in structure.weeks
        for workout_session in week.sessions
        for prescription in workout_session.prescriptions
    }
    exercises = exercises_repo.list_system_exercises_by_names(
        session, list(exercise_names)
    )
    exercise_id_by_name = {exercise.name: exercise.id for exercise in exercises}
    missing = exercise_names - exercise_id_by_name.keys()
    if missing:
        raise TemplateExerciseNotFoundError(sorted(missing))

    name = payload.name or template.name
    return programs_repo.create_program_from_template_structure(
        session,
        user_id=user_id,
        name=name,
        weight_unit=template.weight_unit,
        description=template.description,
        default_progression_type=template.default_progression_type,
        default_progression_params=template.default_progression_params,
        structure=structure,
        exercise_id_by_name=exercise_id_by_name,
    )

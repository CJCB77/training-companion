import pytest
from sqlmodel import select

from app.models.exercise import Exercise
from app.repositories import exercises as exercises_repo
from app.repositories import program_templates as program_templates_repo
from tests.factories import make_exercise, make_profile, make_program_template

pytestmark = pytest.mark.integration


def _persist(session, *objs):
    for obj in objs:
        session.add(obj)
    session.flush()


def test_list_program_templates_returns_all_templates_ordered_by_name(db_session):
    template_b = make_program_template(slug="template-b", name="B Template")
    template_a = make_program_template(slug="template-a", name="A Template")
    _persist(db_session, template_b, template_a)

    listed = program_templates_repo.list_program_templates(db_session)

    names = [template.name for template in listed]
    assert names.index("A Template") < names.index("B Template")


def test_get_program_template_returns_the_matching_template(db_session):
    template = make_program_template(slug="a-template", name="A Template")
    _persist(db_session, template)

    fetched = program_templates_repo.get_program_template(db_session, template.id)

    assert fetched is not None
    assert fetched.slug == "a-template"


def test_get_program_template_for_unknown_id_returns_none(db_session):
    fetched = program_templates_repo.get_program_template(db_session, 999_999)

    assert fetched is None


def test_list_system_exercises_by_names_ignores_a_users_custom_exercise_collision(
    db_session,
):
    user = make_profile()
    _persist(db_session, user)
    custom_squat = make_exercise(name="Squat", created_by_user_id=user.id)
    _persist(db_session, custom_squat)
    system_squat = db_session.exec(
        select(Exercise).where(
            Exercise.name == "Squat", Exercise.created_by_user_id.is_(None)
        )
    ).one()

    resolved = exercises_repo.list_system_exercises_by_names(db_session, ["Squat"])

    assert len(resolved) == 1
    assert resolved[0].id == system_squat.id
    assert resolved[0].id != custom_squat.id


def test_list_system_exercises_by_names_returns_empty_list_for_empty_input(
    db_session,
):
    resolved = exercises_repo.list_system_exercises_by_names(db_session, [])

    assert resolved == []

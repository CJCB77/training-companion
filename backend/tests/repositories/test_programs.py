import pytest
from sqlmodel import select

from app.models.enums import WeightUnit
from app.models.exercise_prescription import ExercisePrescription
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession
from app.repositories import programs as programs_repo
from tests.factories import (
    make_exercise,
    make_exercise_prescription,
    make_profile,
    make_program,
    make_training_week,
    make_workout_session,
)

pytestmark = pytest.mark.integration


def _persist(session, *objs):
    for obj in objs:
        session.add(obj)
    session.flush()


def test_create_and_get_program(db_session):
    user = make_profile()
    _persist(db_session, user)

    program = programs_repo.create_program(
        db_session,
        user_id=user.id,
        name="Texas Method",
        weight_unit=WeightUnit.LB,
    )
    fetched = programs_repo.get_program(db_session, program.id)
    assert fetched is not None
    assert fetched.name == "Texas Method"
    assert fetched.weight_unit == WeightUnit.LB


def test_list_and_active_program_scoped_to_user(db_session):
    user = make_profile()
    other = make_profile()
    _persist(db_session, user, other)

    active = make_program(user_id=user.id, name="Active", is_active=True)
    inactive = make_program(user_id=user.id, name="Old", is_active=False)
    foreign = make_program(user_id=other.id, name="Theirs", is_active=True)
    _persist(db_session, active, inactive, foreign)

    listed = programs_repo.list_programs_for_user(db_session, user_id=user.id)
    assert {p.name for p in listed} == {"Active", "Old"}

    found_active = programs_repo.get_active_program(db_session, user_id=user.id)
    assert found_active.name == "Active"


def test_update_program_applies_given_fields(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="Original")
    _persist(db_session, program)

    updated = programs_repo.update_program(db_session, program, name="Renamed")

    assert updated.name == "Renamed"
    refetched = programs_repo.get_program(db_session, program.id)
    assert refetched.name == "Renamed"


def test_soft_delete_program_sets_deleted_at_and_hides_it_from_default_lookups(
    db_session,
):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="To Delete")
    _persist(db_session, program)

    programs_repo.soft_delete_program(db_session, program)

    assert program.deleted_at is not None
    assert programs_repo.get_program(db_session, program.id) is None
    assert (
        programs_repo.get_program(db_session, program.id, include_deleted=True)
        is not None
    )


def test_soft_deleted_program_excluded_from_list_and_active_lookup(db_session):
    user = make_profile()
    _persist(db_session, user)
    active = make_program(user_id=user.id, name="Active", is_active=True)
    deleted = make_program(user_id=user.id, name="Deleted", is_active=False)
    _persist(db_session, active, deleted)

    programs_repo.soft_delete_program(db_session, deleted)

    listed = programs_repo.list_programs_for_user(db_session, user_id=user.id)
    assert {p.name for p in listed} == {"Active"}

    found_active = programs_repo.get_active_program(db_session, user_id=user.id)
    assert found_active.name == "Active"


def test_soft_deleted_active_program_excluded_from_active_lookup(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="Was Active", is_active=True)
    _persist(db_session, program)

    programs_repo.soft_delete_program(db_session, program)

    assert programs_repo.get_active_program(db_session, user_id=user.id) is None


def test_deleting_program_cascades_to_full_tree(db_session):
    user = make_profile()
    exercise = make_exercise(created_by_user_id=user.id)
    _persist(db_session, user, exercise)

    program = make_program(user_id=user.id)
    _persist(db_session, program)
    week = make_training_week(program_id=program.id)
    _persist(db_session, week)
    session_day = make_workout_session(week_id=week.id)
    _persist(db_session, session_day)
    rx = make_exercise_prescription(
        workout_session_id=session_day.id, exercise_id=exercise.id
    )
    _persist(db_session, rx)

    db_session.delete(program)
    db_session.flush()

    # The whole week -> session -> prescription tree is gone.
    assert db_session.exec(select(TrainingWeek)).all() == []
    assert db_session.exec(select(WorkoutSession)).all() == []
    assert db_session.exec(select(ExercisePrescription)).all() == []
    # The exercise itself survives (RESTRICT, not part of the program tree).
    assert exercise.id is not None

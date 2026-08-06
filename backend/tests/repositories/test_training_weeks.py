import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.workout_session import WorkoutSession
from app.repositories import training_weeks as training_weeks_repo
from tests.factories import (
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


def test_create_and_get_training_week(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id)
    _persist(db_session, program)

    week = training_weeks_repo.create_training_week(
        db_session, program_id=program.id, week_number=1, name="Week 1"
    )
    fetched = training_weeks_repo.get_training_week(db_session, week.id)

    assert fetched is not None
    assert fetched.week_number == 1
    assert fetched.name == "Week 1"


def test_get_training_week_with_owner_returns_the_owning_programs_user_id(
    db_session,
):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id)
    _persist(db_session, program)
    week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, week)

    result = training_weeks_repo.get_training_week_with_owner(db_session, week.id)

    assert result is not None
    fetched_week, owner_user_id = result
    assert fetched_week.id == week.id
    assert owner_user_id == user.id


def test_get_training_week_with_owner_for_missing_week_returns_none(db_session):
    result = training_weeks_repo.get_training_week_with_owner(db_session, 999_999)

    assert result is None


def test_list_training_weeks_for_program_orders_by_week_number(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id)
    _persist(db_session, program)
    week_two = make_training_week(program_id=program.id, week_number=2)
    week_one = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, week_two, week_one)

    listed = training_weeks_repo.list_training_weeks_for_program(db_session, program.id)

    assert [week.week_number for week in listed] == [1, 2]


def test_get_max_week_number_returns_none_when_program_has_no_weeks(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id)
    _persist(db_session, program)

    assert training_weeks_repo.get_max_week_number(db_session, program.id) is None


def test_get_max_week_number_returns_the_highest_week_number(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id)
    _persist(db_session, program)
    _persist(
        db_session,
        make_training_week(program_id=program.id, week_number=1),
        make_training_week(program_id=program.id, week_number=3),
    )

    assert training_weeks_repo.get_max_week_number(db_session, program.id) == 3


def test_create_training_week_with_duplicate_week_number_raises_integrity_error(
    db_session,
):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id)
    _persist(db_session, program)
    training_weeks_repo.create_training_week(
        db_session, program_id=program.id, week_number=1
    )

    with pytest.raises(IntegrityError):
        training_weeks_repo.create_training_week(
            db_session, program_id=program.id, week_number=1
        )


def test_update_training_week_with_disallowed_field_raises_value_error(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id)
    _persist(db_session, program)
    week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, week)

    with pytest.raises(ValueError):
        training_weeks_repo.update_training_week(
            db_session, week, program_id=program.id + 1
        )


def test_delete_training_week_cascades_to_its_workout_sessions(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id)
    _persist(db_session, program)
    week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, week)
    other_week = make_training_week(program_id=program.id, week_number=2)
    _persist(db_session, other_week)
    deleted_session = make_workout_session(week_id=week.id)
    surviving_session = make_workout_session(week_id=other_week.id)
    _persist(db_session, deleted_session, surviving_session)

    training_weeks_repo.delete_training_week(db_session, week)

    remaining_session_week_ids = {
        session.week_id for session in db_session.exec(select(WorkoutSession)).all()
    }
    assert remaining_session_week_ids == {other_week.id}

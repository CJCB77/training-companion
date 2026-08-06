import pytest
from sqlmodel import select

from app.models.exercise_prescription import ExercisePrescription
from app.repositories import workout_sessions as workout_sessions_repo
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


def _make_week(session, *, user=None):
    user = user or make_profile()
    _persist(session, user)
    program = make_program(user_id=user.id)
    _persist(session, program)
    week = make_training_week(program_id=program.id, week_number=1)
    _persist(session, week)
    return user, week


def test_create_and_get_workout_session(db_session):
    _, week = _make_week(db_session)

    workout_session = workout_sessions_repo.create_workout_session(
        db_session, week_id=week.id, day_name="Day A", order_index=0
    )
    fetched = workout_sessions_repo.get_workout_session(db_session, workout_session.id)

    assert fetched is not None
    assert fetched.day_name == "Day A"


def test_get_workout_session_with_owner_returns_the_owning_programs_user_id(
    db_session,
):
    user, week = _make_week(db_session)
    workout_session = make_workout_session(week_id=week.id)
    _persist(db_session, workout_session)

    result = workout_sessions_repo.get_workout_session_with_owner(
        db_session, workout_session.id
    )

    assert result is not None
    fetched_session, owner_user_id = result
    assert fetched_session.id == workout_session.id
    assert owner_user_id == user.id


def test_get_workout_session_with_owner_for_missing_session_returns_none(db_session):
    result = workout_sessions_repo.get_workout_session_with_owner(db_session, 999_999)

    assert result is None


def test_list_workout_sessions_for_week_orders_by_order_index_then_id(db_session):
    _, week = _make_week(db_session)
    tied_first = make_workout_session(week_id=week.id, day_name="A", order_index=1)
    _persist(db_session, tied_first)
    tied_second = make_workout_session(week_id=week.id, day_name="B", order_index=1)
    _persist(db_session, tied_second)
    earliest = make_workout_session(week_id=week.id, day_name="C", order_index=0)
    _persist(db_session, earliest)

    listed = workout_sessions_repo.list_workout_sessions_for_week(db_session, week.id)

    assert [session.day_name for session in listed] == ["C", "A", "B"]


def test_get_max_order_index_returns_none_when_week_has_no_sessions(db_session):
    _, week = _make_week(db_session)

    assert workout_sessions_repo.get_max_order_index(db_session, week.id) is None


def test_get_max_order_index_returns_the_highest_order_index(db_session):
    _, week = _make_week(db_session)
    _persist(
        db_session,
        make_workout_session(week_id=week.id, order_index=0),
        make_workout_session(week_id=week.id, order_index=5),
    )

    assert workout_sessions_repo.get_max_order_index(db_session, week.id) == 5


def test_update_workout_session_with_disallowed_field_raises_value_error(db_session):
    _, week = _make_week(db_session)
    workout_session = make_workout_session(week_id=week.id)
    _persist(db_session, workout_session)

    with pytest.raises(ValueError):
        workout_sessions_repo.update_workout_session(
            db_session, workout_session, week_id=week.id + 1
        )


def test_delete_workout_session_cascades_to_its_exercise_prescriptions(db_session):
    user, week = _make_week(db_session)
    exercise = make_exercise(created_by_user_id=user.id)
    _persist(db_session, exercise)
    workout_session = make_workout_session(week_id=week.id)
    _persist(db_session, workout_session)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id, exercise_id=exercise.id
    )
    _persist(db_session, prescription)

    workout_sessions_repo.delete_workout_session(db_session, workout_session)

    assert db_session.exec(select(ExercisePrescription)).all() == []


def test_start_workout_session_sets_started_at(db_session):
    _, week = _make_week(db_session)
    workout_session = make_workout_session(week_id=week.id)
    _persist(db_session, workout_session)

    started = workout_sessions_repo.start_workout_session(db_session, workout_session)

    assert started.started_at is not None


def test_start_workout_session_is_idempotent_and_keeps_original_timestamp(db_session):
    _, week = _make_week(db_session)
    workout_session = make_workout_session(week_id=week.id)
    _persist(db_session, workout_session)
    first_start = workout_sessions_repo.start_workout_session(
        db_session, workout_session
    )
    original_started_at = first_start.started_at

    restarted = workout_sessions_repo.start_workout_session(db_session, workout_session)

    assert restarted.started_at == original_started_at


def test_complete_workout_session_sets_completed_at(db_session):
    _, week = _make_week(db_session)
    workout_session = make_workout_session(week_id=week.id)
    _persist(db_session, workout_session)

    completed = workout_sessions_repo.complete_workout_session(
        db_session, workout_session
    )

    assert completed.completed_at is not None


def test_complete_workout_session_is_idempotent_and_keeps_original_timestamp(
    db_session,
):
    _, week = _make_week(db_session)
    workout_session = make_workout_session(week_id=week.id)
    _persist(db_session, workout_session)
    first_complete = workout_sessions_repo.complete_workout_session(
        db_session, workout_session
    )
    original_completed_at = first_complete.completed_at

    recompleted = workout_sessions_repo.complete_workout_session(
        db_session, workout_session
    )

    assert recompleted.completed_at == original_completed_at

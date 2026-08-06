import pytest

from app.repositories import exercise_prescriptions as exercise_prescriptions_repo
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


def _make_session(session, *, user=None):
    user = user or make_profile()
    exercise = make_exercise(created_by_user_id=user.id)
    _persist(session, user, exercise)
    program = make_program(user_id=user.id)
    _persist(session, program)
    week = make_training_week(program_id=program.id, week_number=1)
    _persist(session, week)
    workout_session = make_workout_session(week_id=week.id)
    _persist(session, workout_session)
    return user, workout_session, exercise


def test_create_and_get_exercise_prescription(db_session):
    _, workout_session, exercise = _make_session(db_session)

    prescription = exercise_prescriptions_repo.create_exercise_prescription(
        db_session,
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        order_index=0,
        target_sets=5,
        target_reps=5,
    )
    fetched = exercise_prescriptions_repo.get_exercise_prescription(
        db_session, prescription.id
    )

    assert fetched is not None
    assert fetched.exercise_id == exercise.id


def test_get_exercise_prescription_with_owner_returns_the_owning_programs_user_id(
    db_session,
):
    user, workout_session, exercise = _make_session(db_session)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id, exercise_id=exercise.id
    )
    _persist(db_session, prescription)

    result = exercise_prescriptions_repo.get_exercise_prescription_with_owner(
        db_session, prescription.id
    )

    assert result is not None
    fetched_prescription, owner_user_id = result
    assert fetched_prescription.id == prescription.id
    assert owner_user_id == user.id


def test_get_exercise_prescription_with_owner_for_missing_prescription_returns_none(
    db_session,
):
    result = exercise_prescriptions_repo.get_exercise_prescription_with_owner(
        db_session, 999_999
    )

    assert result is None


def test_list_exercise_prescriptions_for_session_orders_by_order_index_then_id(
    db_session,
):
    _, workout_session, exercise = _make_session(db_session)
    tied_first = make_exercise_prescription(
        workout_session_id=workout_session.id, exercise_id=exercise.id, order_index=1
    )
    _persist(db_session, tied_first)
    tied_second = make_exercise_prescription(
        workout_session_id=workout_session.id, exercise_id=exercise.id, order_index=1
    )
    _persist(db_session, tied_second)
    earliest = make_exercise_prescription(
        workout_session_id=workout_session.id, exercise_id=exercise.id, order_index=0
    )
    _persist(db_session, earliest)

    listed = exercise_prescriptions_repo.list_exercise_prescriptions_for_session(
        db_session, workout_session.id
    )

    assert [prescription.id for prescription in listed] == [
        earliest.id,
        tied_first.id,
        tied_second.id,
    ]


def test_get_max_order_index_returns_none_when_session_has_no_prescriptions(
    db_session,
):
    _, workout_session, _exercise = _make_session(db_session)

    assert (
        exercise_prescriptions_repo.get_max_order_index(db_session, workout_session.id)
        is None
    )


def test_get_max_order_index_returns_the_highest_order_index(db_session):
    _, workout_session, exercise = _make_session(db_session)
    _persist(
        db_session,
        make_exercise_prescription(
            workout_session_id=workout_session.id,
            exercise_id=exercise.id,
            order_index=0,
        ),
        make_exercise_prescription(
            workout_session_id=workout_session.id,
            exercise_id=exercise.id,
            order_index=4,
        ),
    )

    assert (
        exercise_prescriptions_repo.get_max_order_index(db_session, workout_session.id)
        == 4
    )


def test_update_exercise_prescription_with_disallowed_field_raises_value_error(
    db_session,
):
    _, workout_session, exercise = _make_session(db_session)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id, exercise_id=exercise.id
    )
    _persist(db_session, prescription)

    with pytest.raises(ValueError):
        exercise_prescriptions_repo.update_exercise_prescription(
            db_session, prescription, workout_session_id=workout_session.id + 1
        )


def test_delete_exercise_prescription_leaves_its_exercise_untouched(db_session):
    _, workout_session, exercise = _make_session(db_session)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id, exercise_id=exercise.id
    )
    _persist(db_session, prescription)

    exercise_prescriptions_repo.delete_exercise_prescription(db_session, prescription)

    assert (
        exercise_prescriptions_repo.get_exercise_prescription(
            db_session, prescription.id
        )
        is None
    )
    assert db_session.get(type(exercise), exercise.id) is not None

import pytest

from app.models.enums import SetCompletionState
from app.repositories import exercise_performances as exercise_performances_repo
from tests.factories import (
    make_exercise,
    make_exercise_performance,
    make_exercise_prescription,
    make_profile,
    make_program,
    make_progression_line,
    make_training_week,
    make_workout_session,
)

pytestmark = pytest.mark.integration


def _persist(session, *objs):
    for obj in objs:
        session.add(obj)
    session.flush()


def _make_prescription(session, *, user=None):
    user = user or make_profile()
    exercise = make_exercise(created_by_user_id=user.id)
    _persist(session, user, exercise)
    program = make_program(user_id=user.id)
    _persist(session, program)
    week = make_training_week(program_id=program.id, week_number=1)
    _persist(session, week)
    workout_session = make_workout_session(week_id=week.id)
    _persist(session, workout_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(session, line)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
    )
    _persist(session, prescription)
    return user, workout_session, prescription, program


def test_create_and_get_exercise_performance(db_session):
    _, _workout_session, prescription, _program = _make_prescription(db_session)

    performance = exercise_performances_repo.create_exercise_performance(
        db_session,
        prescription_id=prescription.id,
        set_number=1,
        actual_reps=5,
        completion_state=SetCompletionState.COMPLETED,
    )
    fetched = exercise_performances_repo.get_exercise_performance(
        db_session, performance.id
    )

    assert fetched is not None
    assert fetched.prescription_id == prescription.id


def test_get_exercise_performance_with_owner_returns_the_owning_programs_user_id(
    db_session,
):
    user, _workout_session, prescription, _program = _make_prescription(db_session)
    performance = make_exercise_performance(prescription_id=prescription.id)
    _persist(db_session, performance)

    result = exercise_performances_repo.get_exercise_performance_with_owner(
        db_session, performance.id
    )

    assert result is not None
    fetched_performance, owner_user_id = result
    assert fetched_performance.id == performance.id
    assert owner_user_id == user.id


def test_get_exercise_performance_with_owner_for_missing_performance_returns_none(
    db_session,
):
    result = exercise_performances_repo.get_exercise_performance_with_owner(
        db_session, 999_999
    )

    assert result is None


def test_list_performances_for_prescription_orders_by_set_number_then_id(db_session):
    _, _workout_session, prescription, _program = _make_prescription(db_session)
    tied_first = make_exercise_performance(
        prescription_id=prescription.id, set_number=2
    )
    _persist(db_session, tied_first)
    tied_second = make_exercise_performance(
        prescription_id=prescription.id, set_number=2
    )
    _persist(db_session, tied_second)
    earliest = make_exercise_performance(prescription_id=prescription.id, set_number=1)
    _persist(db_session, earliest)

    listed = exercise_performances_repo.list_performances_for_prescription(
        db_session, prescription.id
    )

    assert [performance.id for performance in listed] == [
        earliest.id,
        tied_first.id,
        tied_second.id,
    ]


def test_list_performances_for_session_orders_by_prescription_then_set_number(
    db_session,
):
    user, workout_session, first_prescription, program = _make_prescription(db_session)
    second_exercise = make_exercise(created_by_user_id=user.id)
    _persist(db_session, second_exercise)
    second_line = make_progression_line(
        program_id=program.id, exercise_id=second_exercise.id
    )
    _persist(db_session, second_line)
    second_prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=second_exercise.id,
        progression_line_id=second_line.id,
        order_index=1,
    )
    _persist(db_session, second_prescription)
    second_prescription_performance = make_exercise_performance(
        prescription_id=second_prescription.id, set_number=1
    )
    _persist(db_session, second_prescription_performance)
    first_prescription_performance = make_exercise_performance(
        prescription_id=first_prescription.id, set_number=1
    )
    _persist(db_session, first_prescription_performance)

    listed = exercise_performances_repo.list_performances_for_session(
        db_session, workout_session.id
    )

    assert [performance.id for performance in listed] == [
        first_prescription_performance.id,
        second_prescription_performance.id,
    ]


def test_get_max_set_number_returns_none_when_prescription_has_no_performances(
    db_session,
):
    _, _workout_session, prescription, _program = _make_prescription(db_session)

    assert (
        exercise_performances_repo.get_max_set_number(db_session, prescription.id)
        is None
    )


def test_get_max_set_number_returns_the_highest_set_number(db_session):
    _, _workout_session, prescription, _program = _make_prescription(db_session)
    _persist(
        db_session,
        make_exercise_performance(prescription_id=prescription.id, set_number=1),
        make_exercise_performance(prescription_id=prescription.id, set_number=3),
    )

    assert (
        exercise_performances_repo.get_max_set_number(db_session, prescription.id) == 3
    )


def test_update_exercise_performance_with_disallowed_field_raises_value_error(
    db_session,
):
    _, _workout_session, prescription, _program = _make_prescription(db_session)
    performance = make_exercise_performance(prescription_id=prescription.id)
    _persist(db_session, performance)

    with pytest.raises(ValueError):
        exercise_performances_repo.update_exercise_performance(
            db_session, performance, prescription_id=prescription.id + 1
        )


def test_delete_exercise_performance_leaves_its_prescription_untouched(db_session):
    _, _workout_session, prescription, _program = _make_prescription(db_session)
    performance = make_exercise_performance(prescription_id=prescription.id)
    _persist(db_session, performance)

    exercise_performances_repo.delete_exercise_performance(db_session, performance)

    assert (
        exercise_performances_repo.get_exercise_performance(db_session, performance.id)
        is None
    )
    assert db_session.get(type(prescription), prescription.id) is not None


def test_deleting_prescription_cascades_to_its_performances(db_session):
    from app.repositories import exercise_prescriptions as exercise_prescriptions_repo

    _, _workout_session, prescription, _program = _make_prescription(db_session)
    performance = make_exercise_performance(prescription_id=prescription.id)
    _persist(db_session, performance)

    exercise_prescriptions_repo.delete_exercise_prescription(db_session, prescription)

    assert (
        exercise_performances_repo.get_exercise_performance(db_session, performance.id)
        is None
    )

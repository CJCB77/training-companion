from datetime import datetime, timedelta, timezone

import pytest

from app.repositories import dashboard as dashboard_repo
from app.repositories import history as history_repo
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


def _make_prescription(
    session,
    *,
    user=None,
    program=None,
    exercise=None,
    line=None,
    week_number: int = 1,
    order_index: int = 0,
):
    user = user or make_profile()
    exercise = exercise or make_exercise(created_by_user_id=user.id)
    _persist(session, user, exercise)
    program = program or make_program(user_id=user.id)
    _persist(session, program)
    week = make_training_week(program_id=program.id, week_number=week_number)
    _persist(session, week)
    workout_session = make_workout_session(week_id=week.id, order_index=order_index)
    _persist(session, workout_session)
    # A given (program, exercise) pair can only have one *default* line —
    # reuse the caller's line when they're re-prescribing the same exercise
    # in the same program, rather than violating that uniqueness.
    if line is None:
        line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
        _persist(session, line)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
    )
    _persist(session, prescription)
    return user, workout_session, prescription, program, exercise, line


# --------------------------------------------------------------------------
# list_program_sessions
# --------------------------------------------------------------------------


def test_list_program_sessions_orders_by_week_number_then_order_index(db_session):
    user, _s, _p, program, exercise, line = _make_prescription(
        db_session, week_number=2, order_index=1
    )
    _u2, second_session, _p2, _prog2, _e2, _l2 = _make_prescription(
        db_session,
        user=user,
        program=program,
        exercise=exercise,
        line=line,
        week_number=1,
        order_index=0,
    )

    rows = dashboard_repo.list_program_sessions(db_session, program_id=program.id)

    assert [row[0].id for row in rows] == [second_session.id, rows[1][0].id]
    assert rows[0][1] == 1  # week_number for the first (earlier) row


def test_list_program_sessions_counts_prescriptions_per_session(db_session):
    user, workout_session, _p, program, exercise, line = _make_prescription(db_session)
    second_prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        order_index=1,
    )
    _persist(db_session, second_prescription)

    rows = dashboard_repo.list_program_sessions(db_session, program_id=program.id)

    assert len(rows) == 1
    _session, _week_number, prescription_count = rows[0]
    assert prescription_count == 2


# --------------------------------------------------------------------------
# list_completed_at_since / get_last_completed_at
# --------------------------------------------------------------------------


def test_list_completed_at_since_excludes_sessions_before_the_cutoff(db_session):
    user, workout_session, _p, _program, _exercise, _line = _make_prescription(
        db_session
    )
    workout_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(workout_session)
    db_session.flush()

    result = dashboard_repo.list_completed_at_since(
        db_session, user_id=user.id, since=datetime(2026, 1, 2, tzinfo=timezone.utc)
    )

    assert result == []


def test_list_completed_at_since_excludes_other_users_sessions(db_session):
    owner, owner_session, _p, _prog, _e, _l = _make_prescription(db_session)
    owner_session.completed_at = datetime(2026, 1, 5, tzinfo=timezone.utc)
    db_session.add(owner_session)
    _other_user, other_session, _p2, _prog2, _e2, _l2 = _make_prescription(db_session)
    other_session.completed_at = datetime(2026, 1, 5, tzinfo=timezone.utc)
    db_session.add(other_session)
    db_session.flush()

    result = dashboard_repo.list_completed_at_since(
        db_session, user_id=owner.id, since=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )

    assert result == [owner_session.completed_at]


def test_get_last_completed_at_returns_the_most_recent_completion(db_session):
    user, older_session, _p, program, exercise, line = _make_prescription(db_session)
    older_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(older_session)
    _u2, newer_session, _p2, _prog2, _e2, _l2 = _make_prescription(
        db_session,
        user=user,
        program=program,
        exercise=exercise,
        line=line,
        week_number=2,
    )
    newer_session.completed_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    db_session.add(newer_session)
    db_session.flush()

    result = dashboard_repo.get_last_completed_at(db_session, user_id=user.id)

    assert result == newer_session.completed_at


def test_get_last_completed_at_with_nothing_completed_returns_none(db_session):
    user, _s, _p, _program, _exercise, _line = _make_prescription(db_session)

    result = dashboard_repo.get_last_completed_at(db_session, user_id=user.id)

    assert result is None


# --------------------------------------------------------------------------
# list_recent_exercise_ids
# --------------------------------------------------------------------------


def test_list_recent_exercise_ids_excludes_exercises_from_incomplete_sessions(
    db_session,
):
    user, _workout_session, _p, _program, exercise, _line = _make_prescription(
        db_session
    )
    # workout_session.completed_at left None.

    result = dashboard_repo.list_recent_exercise_ids(
        db_session,
        user_id=user.id,
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert exercise.id not in result


def test_list_recent_exercise_ids_includes_exercises_from_recently_completed_sessions(
    db_session,
):
    user, workout_session, _p, _program, exercise, _line = _make_prescription(
        db_session
    )
    workout_session.completed_at = datetime.now(timezone.utc)
    db_session.add(workout_session)
    db_session.flush()

    result = dashboard_repo.list_recent_exercise_ids(
        db_session,
        user_id=user.id,
        since=datetime.now(timezone.utc) - timedelta(days=28),
    )

    assert result == [exercise.id]


def test_list_recent_exercise_ids_excludes_other_users_exercises(db_session):
    owner, owner_session, _p, _prog, owner_exercise, _l = _make_prescription(db_session)
    owner_session.completed_at = datetime.now(timezone.utc)
    db_session.add(owner_session)
    _other_user, other_session, _p2, _prog2, other_exercise, _l2 = _make_prescription(
        db_session
    )
    other_session.completed_at = datetime.now(timezone.utc)
    db_session.add(other_session)
    db_session.flush()

    result = dashboard_repo.list_recent_exercise_ids(
        db_session,
        user_id=owner.id,
        since=datetime.now(timezone.utc) - timedelta(days=28),
    )

    assert result == [owner_exercise.id]
    assert other_exercise.id not in result


# --------------------------------------------------------------------------
# history_repo.list_weighted_performances_for_exercises (additive, TRAIN-22)
# --------------------------------------------------------------------------


def test_list_weighted_performances_for_exercises_groups_rows_by_exercise(db_session):
    user, workout_session, prescription, program, exercise, _line = _make_prescription(
        db_session
    )
    workout_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(workout_session)
    other_exercise = make_exercise(created_by_user_id=user.id)
    _persist(db_session, other_exercise)
    other_line = make_progression_line(
        program_id=program.id, exercise_id=other_exercise.id
    )
    _persist(db_session, other_line)
    other_prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=other_exercise.id,
        progression_line_id=other_line.id,
        order_index=1,
    )
    _persist(db_session, other_prescription)
    performance = make_exercise_performance(prescription_id=prescription.id)
    other_performance = make_exercise_performance(prescription_id=other_prescription.id)
    _persist(db_session, performance, other_performance)

    rows = history_repo.list_weighted_performances_for_exercises(
        db_session, user_id=user.id, exercise_ids=[exercise.id, other_exercise.id]
    )

    returned_exercise_ids = {row[0] for row in rows}
    assert returned_exercise_ids == {exercise.id, other_exercise.id}


def test_list_weighted_performances_for_exercises_orders_oldest_first(db_session):
    user, workout_session, prescription, program, exercise, _line = _make_prescription(
        db_session
    )
    workout_session.completed_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    db_session.add(workout_session)
    earlier_week = make_training_week(program_id=program.id, week_number=0)
    _persist(db_session, earlier_week)
    earlier_session = make_workout_session(week_id=earlier_week.id)
    earlier_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _persist(db_session, earlier_session)
    earlier_prescription = make_exercise_prescription(
        workout_session_id=earlier_session.id,
        exercise_id=exercise.id,
        progression_line_id=prescription.progression_line_id,
    )
    _persist(db_session, earlier_prescription)
    later_performance = make_exercise_performance(prescription_id=prescription.id)
    earlier_performance = make_exercise_performance(
        prescription_id=earlier_prescription.id
    )
    _persist(db_session, later_performance, earlier_performance)

    rows = history_repo.list_weighted_performances_for_exercises(
        db_session, user_id=user.id, exercise_ids=[exercise.id]
    )

    completed_ats = [row[5] for row in rows]
    assert completed_ats == sorted(completed_ats)


def test_list_weighted_performances_for_exercises_with_empty_ids_returns_empty(
    db_session,
):
    result = history_repo.list_weighted_performances_for_exercises(
        db_session, user_id=1, exercise_ids=[]
    )

    assert result == []


def test_list_weighted_performances_for_exercises_excludes_other_users_data(
    db_session,
):
    owner, owner_session, owner_prescription, _prog, owner_exercise, _l = (
        _make_prescription(db_session)
    )
    owner_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(owner_session)
    owner_performance = make_exercise_performance(prescription_id=owner_prescription.id)
    _persist(db_session, owner_performance)

    _other_user, other_session, other_prescription, _prog2, other_exercise, _l2 = (
        _make_prescription(db_session)
    )
    other_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(other_session)
    other_performance = make_exercise_performance(prescription_id=other_prescription.id)
    _persist(db_session, other_performance)

    rows = history_repo.list_weighted_performances_for_exercises(
        db_session,
        user_id=owner.id,
        exercise_ids=[owner_exercise.id, other_exercise.id],
    )

    returned_exercise_ids = {row[0] for row in rows}
    assert returned_exercise_ids == {owner_exercise.id}
    assert other_exercise.id not in returned_exercise_ids

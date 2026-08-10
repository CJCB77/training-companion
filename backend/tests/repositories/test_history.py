from datetime import datetime, timezone

import pytest

from app.models.enums import SetCompletionState, WeightUnit
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
    session, *, user=None, program=None, exercise=None, **program_overrides
):
    user = user or make_profile()
    exercise = exercise or make_exercise(created_by_user_id=user.id)
    _persist(session, user, exercise)
    program = program or make_program(user_id=user.id, **program_overrides)
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
    return user, workout_session, prescription, program, exercise, line


def test_list_completed_sessions_excludes_sessions_never_completed(db_session):
    user, workout_session, _prescription, _program, _exercise, _line = (
        _make_prescription(db_session)
    )
    workout_session.completed_at = None
    db_session.add(workout_session)
    db_session.flush()

    result = history_repo.list_completed_sessions(
        db_session, user_id=user.id, program_id=None, limit=50, offset=0
    )

    assert result == []


def test_list_completed_sessions_returns_owned_sessions_newest_first(db_session):
    user, first_session, _p1, program, exercise, _line = _make_prescription(db_session)
    first_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(first_session)
    week = make_training_week(program_id=program.id, week_number=2)
    _persist(db_session, week)
    second_session = make_workout_session(week_id=week.id)
    second_session.completed_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    _persist(db_session, second_session)
    db_session.flush()

    result = history_repo.list_completed_sessions(
        db_session, user_id=user.id, program_id=None, limit=50, offset=0
    )

    assert [workout_session.id for workout_session, _program_id in result] == [
        second_session.id,
        first_session.id,
    ]


def test_list_completed_sessions_excludes_other_users_sessions(db_session):
    owner, owner_session, _p, _program, _exercise, _line = _make_prescription(
        db_session
    )
    owner_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(owner_session)
    other_user, other_session, _p2, _program2, _e2, _l2 = _make_prescription(db_session)
    other_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(other_session)
    db_session.flush()

    result = history_repo.list_completed_sessions(
        db_session, user_id=owner.id, program_id=None, limit=50, offset=0
    )

    assert [workout_session.id for workout_session, _program_id in result] == [
        owner_session.id
    ]


def test_list_weighted_performances_for_exercise_excludes_skipped_sets(db_session):
    user, workout_session, prescription, _program, exercise, _line = _make_prescription(
        db_session
    )
    workout_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(workout_session)
    skipped = make_exercise_performance(
        prescription_id=prescription.id,
        completion_state=SetCompletionState.SKIPPED,
    )
    _persist(db_session, skipped)

    result = history_repo.list_weighted_performances_for_exercise(
        db_session, user_id=user.id, exercise_id=exercise.id
    )

    assert result == []


def test_list_weighted_performances_for_exercise_excludes_bodyweight_sets(db_session):
    user, workout_session, prescription, _program, exercise, _line = _make_prescription(
        db_session
    )
    workout_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(workout_session)
    bodyweight_set = make_exercise_performance(
        prescription_id=prescription.id,
        actual_weight=None,
    )
    _persist(db_session, bodyweight_set)

    result = history_repo.list_weighted_performances_for_exercise(
        db_session, user_id=user.id, exercise_id=exercise.id
    )

    assert result == []


def test_list_weighted_performances_for_exercise_includes_failed_sets(db_session):
    user, workout_session, prescription, program, exercise, line = _make_prescription(
        db_session
    )
    workout_session.completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add(workout_session)
    failed_set = make_exercise_performance(
        prescription_id=prescription.id,
        completion_state=SetCompletionState.FAILED,
        actual_weight=140.0,
        actual_reps=4,
    )
    _persist(db_session, failed_set)

    result = history_repo.list_weighted_performances_for_exercise(
        db_session, user_id=user.id, exercise_id=exercise.id
    )

    assert len(result) == 1
    weight, reps, weight_unit, completed_at, session_id, program_id, line_id = result[0]
    assert weight == 140.0
    assert reps == 4
    assert weight_unit == WeightUnit.KG
    assert session_id == workout_session.id
    assert program_id == program.id
    assert line_id == line.id


def test_list_weighted_performances_for_exercise_excludes_incomplete_sessions(
    db_session,
):
    user, workout_session, prescription, _program, exercise, _line = _make_prescription(
        db_session
    )
    # workout_session.completed_at left None (never completed).
    performance = make_exercise_performance(prescription_id=prescription.id)
    _persist(db_session, performance)

    result = history_repo.list_weighted_performances_for_exercise(
        db_session, user_id=user.id, exercise_id=exercise.id
    )

    assert result == []

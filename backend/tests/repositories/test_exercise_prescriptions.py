from datetime import datetime, timedelta, timezone

import pytest

from app.repositories import exercise_prescriptions as exercise_prescriptions_repo
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


def _make_session(session, *, user=None):
    """Program + week + workout session + exercise + that exercise's default
    progression line in this program — the line every prescription in this file
    needs now that `progression_line_id` is NOT NULL.
    """
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
    return user, workout_session, exercise, line


def _make_program_and_exercise(session, *, user=None):
    """Like `_make_session`, but stops one level up (program + week, no workout
    session yet) — `list_prior_attempts` tests need to create several sessions
    within the same program. Also creates the exercise's default progression line.
    """
    user = user or make_profile()
    exercise = make_exercise(created_by_user_id=user.id)
    _persist(session, user, exercise)
    program = make_program(user_id=user.id)
    _persist(session, program)
    week = make_training_week(program_id=program.id, week_number=1)
    _persist(session, week)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(session, line)
    return user, program, week, exercise, line


def _completed_session(session, *, week_id, order_index, completed_at):
    workout_session = make_workout_session(
        week_id=week_id, order_index=order_index, completed_at=completed_at
    )
    _persist(session, workout_session)
    return workout_session


def test_create_and_get_exercise_prescription(db_session):
    _, workout_session, exercise, line = _make_session(db_session)

    prescription = exercise_prescriptions_repo.create_exercise_prescription(
        db_session,
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
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
    user, workout_session, exercise, line = _make_session(db_session)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
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
    _, workout_session, exercise, line = _make_session(db_session)
    tied_first = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        order_index=1,
    )
    _persist(db_session, tied_first)
    tied_second = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        order_index=1,
    )
    _persist(db_session, tied_second)
    earliest = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        order_index=0,
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
    _, workout_session, _exercise, _line = _make_session(db_session)

    assert (
        exercise_prescriptions_repo.get_max_order_index(db_session, workout_session.id)
        is None
    )


def test_get_max_order_index_returns_the_highest_order_index(db_session):
    _, workout_session, exercise, line = _make_session(db_session)
    _persist(
        db_session,
        make_exercise_prescription(
            workout_session_id=workout_session.id,
            exercise_id=exercise.id,
            progression_line_id=line.id,
            order_index=0,
        ),
        make_exercise_prescription(
            workout_session_id=workout_session.id,
            exercise_id=exercise.id,
            progression_line_id=line.id,
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
    _, workout_session, exercise, line = _make_session(db_session)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
    )
    _persist(db_session, prescription)

    with pytest.raises(ValueError):
        exercise_prescriptions_repo.update_exercise_prescription(
            db_session, prescription, workout_session_id=workout_session.id + 1
        )


def test_delete_exercise_prescription_leaves_its_exercise_untouched(db_session):
    _, workout_session, exercise, line = _make_session(db_session)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
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


def test_list_prior_attempts_orders_newest_completed_session_first(db_session):
    _, program, week, exercise, line = _make_program_and_exercise(db_session)
    now = datetime.now(timezone.utc)
    older_session = _completed_session(
        db_session, week_id=week.id, order_index=0, completed_at=now - timedelta(days=7)
    )
    newer_session = _completed_session(
        db_session, week_id=week.id, order_index=1, completed_at=now - timedelta(days=1)
    )
    older_prescription = make_exercise_prescription(
        workout_session_id=older_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
    )
    _persist(db_session, older_prescription)
    newer_prescription = make_exercise_prescription(
        workout_session_id=newer_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
    )
    _persist(db_session, newer_prescription)

    rows = exercise_prescriptions_repo.list_prior_attempts(
        db_session,
        program_id=program.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        limit=10,
    )

    assert [prescription.id for prescription, _ in rows] == [
        newer_prescription.id,
        older_prescription.id,
    ]


def test_list_prior_attempts_excludes_sessions_that_are_not_completed(db_session):
    _, program, week, exercise, line = _make_program_and_exercise(db_session)
    completed = _completed_session(
        db_session,
        week_id=week.id,
        order_index=0,
        completed_at=datetime.now(timezone.utc),
    )
    incomplete = make_workout_session(week_id=week.id, order_index=1)
    _persist(db_session, incomplete)
    completed_prescription = make_exercise_prescription(
        workout_session_id=completed.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
    )
    _persist(db_session, completed_prescription)
    incomplete_prescription = make_exercise_prescription(
        workout_session_id=incomplete.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
    )
    _persist(db_session, incomplete_prescription)

    rows = exercise_prescriptions_repo.list_prior_attempts(
        db_session,
        program_id=program.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        limit=10,
    )

    assert [prescription.id for prescription, _ in rows] == [completed_prescription.id]


def test_list_prior_attempts_scoped_to_program_and_exercise(db_session):
    user, program, week, exercise, line = _make_program_and_exercise(db_session)
    other_exercise = make_exercise(created_by_user_id=user.id)
    _persist(db_session, other_exercise)
    other_exercise_line = make_progression_line(
        program_id=program.id, exercise_id=other_exercise.id
    )
    _persist(db_session, other_exercise_line)
    other_program = make_program(user_id=user.id)
    _persist(db_session, other_program)
    other_week = make_training_week(program_id=other_program.id, week_number=1)
    _persist(db_session, other_week)
    other_program_line = make_progression_line(
        program_id=other_program.id, exercise_id=exercise.id
    )
    _persist(db_session, other_program_line)

    now = datetime.now(timezone.utc)
    in_scope_session = _completed_session(
        db_session, week_id=week.id, order_index=0, completed_at=now
    )
    in_scope_prescription = make_exercise_prescription(
        workout_session_id=in_scope_session.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
    )
    _persist(db_session, in_scope_prescription)

    # Same session, different exercise -> out of scope.
    wrong_exercise_prescription = make_exercise_prescription(
        workout_session_id=in_scope_session.id,
        exercise_id=other_exercise.id,
        progression_line_id=other_exercise_line.id,
    )
    _persist(db_session, wrong_exercise_prescription)

    # Same exercise, different program -> out of scope.
    other_program_session = _completed_session(
        db_session, week_id=other_week.id, order_index=0, completed_at=now
    )
    wrong_program_prescription = make_exercise_prescription(
        workout_session_id=other_program_session.id,
        exercise_id=exercise.id,
        progression_line_id=other_program_line.id,
    )
    _persist(db_session, wrong_program_prescription)

    rows = exercise_prescriptions_repo.list_prior_attempts(
        db_session,
        program_id=program.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        limit=10,
    )

    assert [prescription.id for prescription, _ in rows] == [in_scope_prescription.id]


def test_list_prior_attempts_scoped_to_progression_line_never_share_history(
    db_session,
):
    """Two prescriptions of the same exercise in the same program, on different
    lines (a heavy line and a separate explicit light line), must never see each
    other's history — this is the bug TRAIN-26 exists to fix.
    """
    _, program, week, exercise, heavy_line = _make_program_and_exercise(db_session)
    light_line = make_progression_line(
        program_id=program.id, exercise_id=exercise.id, is_default=False, label="Light"
    )
    _persist(db_session, light_line)
    now = datetime.now(timezone.utc)
    heavy_session = _completed_session(
        db_session, week_id=week.id, order_index=0, completed_at=now
    )
    light_session = _completed_session(
        db_session, week_id=week.id, order_index=1, completed_at=now
    )
    heavy_prescription = make_exercise_prescription(
        workout_session_id=heavy_session.id,
        exercise_id=exercise.id,
        progression_line_id=heavy_line.id,
    )
    light_prescription = make_exercise_prescription(
        workout_session_id=light_session.id,
        exercise_id=exercise.id,
        progression_line_id=light_line.id,
    )
    _persist(db_session, heavy_prescription, light_prescription)

    heavy_rows = exercise_prescriptions_repo.list_prior_attempts(
        db_session,
        program_id=program.id,
        exercise_id=exercise.id,
        progression_line_id=heavy_line.id,
        limit=10,
    )
    light_rows = exercise_prescriptions_repo.list_prior_attempts(
        db_session,
        program_id=program.id,
        exercise_id=exercise.id,
        progression_line_id=light_line.id,
        limit=10,
    )

    assert [prescription.id for prescription, _ in heavy_rows] == [
        heavy_prescription.id
    ]
    assert [prescription.id for prescription, _ in light_rows] == [
        light_prescription.id
    ]


def test_list_prior_attempts_on_same_non_default_line_shares_history(db_session):
    """Two prescriptions deliberately placed on the same explicit (non-default)
    line must share history, same as two default-line prescriptions do.
    """
    _, program, week, exercise, _default_line = _make_program_and_exercise(db_session)
    explicit_line = make_progression_line(
        program_id=program.id,
        exercise_id=exercise.id,
        is_default=False,
        label="Squats B",
    )
    _persist(db_session, explicit_line)
    now = datetime.now(timezone.utc)
    older_session = _completed_session(
        db_session, week_id=week.id, order_index=0, completed_at=now - timedelta(days=7)
    )
    newer_session = _completed_session(
        db_session, week_id=week.id, order_index=1, completed_at=now
    )
    older_prescription = make_exercise_prescription(
        workout_session_id=older_session.id,
        exercise_id=exercise.id,
        progression_line_id=explicit_line.id,
    )
    newer_prescription = make_exercise_prescription(
        workout_session_id=newer_session.id,
        exercise_id=exercise.id,
        progression_line_id=explicit_line.id,
    )
    _persist(db_session, older_prescription, newer_prescription)

    rows = exercise_prescriptions_repo.list_prior_attempts(
        db_session,
        program_id=program.id,
        exercise_id=exercise.id,
        progression_line_id=explicit_line.id,
        limit=10,
    )

    assert [prescription.id for prescription, _ in rows] == [
        newer_prescription.id,
        older_prescription.id,
    ]


def test_list_prior_attempts_pairs_each_prescription_with_its_own_performances(
    db_session,
):
    _, program, week, exercise, line = _make_program_and_exercise(db_session)
    session_a = _completed_session(
        db_session,
        week_id=week.id,
        order_index=0,
        completed_at=datetime.now(timezone.utc),
    )
    prescription_a = make_exercise_prescription(
        workout_session_id=session_a.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
    )
    _persist(db_session, prescription_a)
    performance_a1 = make_exercise_performance(
        prescription_id=prescription_a.id, set_number=1
    )
    performance_a2 = make_exercise_performance(
        prescription_id=prescription_a.id, set_number=2
    )
    _persist(db_session, performance_a1, performance_a2)

    session_b = _completed_session(
        db_session,
        week_id=week.id,
        order_index=1,
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    prescription_b = make_exercise_prescription(
        workout_session_id=session_b.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
    )
    _persist(db_session, prescription_b)
    # No performances logged for prescription_b — the row must still come back,
    # paired with an empty list, not be omitted (exclusion of unlogged rows is the
    # service layer's job, in build_attempt_history — this repo function is just
    # the raw pairing).

    rows = exercise_prescriptions_repo.list_prior_attempts(
        db_session,
        program_id=program.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        limit=10,
    )
    performances_by_prescription_id = {
        prescription.id: performances for prescription, performances in rows
    }

    assert {p.id for p in performances_by_prescription_id[prescription_a.id]} == {
        performance_a1.id,
        performance_a2.id,
    }
    assert performances_by_prescription_id[prescription_b.id] == []


def test_list_prior_attempts_respects_the_limit(db_session):
    _, program, week, exercise, line = _make_program_and_exercise(db_session)
    now = datetime.now(timezone.utc)
    for i in range(5):
        session = _completed_session(
            db_session,
            week_id=week.id,
            order_index=i,
            completed_at=now - timedelta(days=i),
        )
        _persist(
            db_session,
            make_exercise_prescription(
                workout_session_id=session.id,
                exercise_id=exercise.id,
                progression_line_id=line.id,
            ),
        )

    rows = exercise_prescriptions_repo.list_prior_attempts(
        db_session,
        program_id=program.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        limit=2,
    )

    assert len(rows) == 2

"""Integration tests for progression-line scoping through the real engine
orchestration (`get_recommendation_for_prescription`) — the actual bug TRAIN-26
exists to fix: a program that trains the same exercise on two lines (e.g. a heavy
day and a separate lighter/volume day) must get two independent recommendations,
never one contaminating the other. Also covers the "label is decorative only"
acceptance criterion end to end, through the real rename endpoint's service.

Real DB, real repositories, real engine — nothing here is mocked, per CLAUDE.md's
"do not mock the progression engine" and this file needing real persisted
history to exercise the scoping query.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import ProgressionType
from app.services import progression as progression_service
from app.services import progression_lines as progression_lines_service
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

TARGET_SETS = 1
TARGET_REPS = 5
HEAVY_WEIGHT = 100.0
LIGHT_WEIGHT = 60.0
INCREMENT = 2.5


def _persist(session, *objs):
    for obj in objs:
        session.add(obj)
    session.flush()


def _build_program(session):
    user = make_profile()
    exercise = make_exercise(created_by_user_id=user.id)
    _persist(session, user, exercise)
    program = make_program(
        user_id=user.id,
        default_progression_type=ProgressionType.FIXED_INCREMENT,
        default_progression_params={"increment": INCREMENT},
    )
    _persist(session, program)
    week = make_training_week(program_id=program.id, week_number=1)
    _persist(session, week)
    return user, program, week, exercise


def _completed_prescription(session, *, week_id, line_id, exercise_id, weight, reps):
    workout_session = make_workout_session(
        week_id=week_id, completed_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    _persist(session, workout_session)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise_id,
        progression_line_id=line_id,
        target_sets=TARGET_SETS,
        target_reps=TARGET_REPS,
        target_weight=weight,
    )
    _persist(session, prescription)
    performance = make_exercise_performance(
        prescription_id=prescription.id,
        actual_reps=reps,
        actual_weight=weight,
    )
    _persist(session, performance)
    return prescription


def _current_prescription(session, *, week_id, line_id, exercise_id, weight):
    workout_session = make_workout_session(week_id=week_id)
    _persist(session, workout_session)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise_id,
        progression_line_id=line_id,
        target_sets=TARGET_SETS,
        target_reps=TARGET_REPS,
        target_weight=weight,
    )
    _persist(session, prescription)
    return prescription


def test_recommendations_for_two_lines_of_the_same_exercise_do_not_contaminate(
    db_session,
):
    user, program, week, exercise = _build_program(db_session)
    heavy_line = make_progression_line(
        program_id=program.id, exercise_id=exercise.id, is_default=True
    )
    light_line = make_progression_line(
        program_id=program.id, exercise_id=exercise.id, is_default=False, label="Light"
    )
    _persist(db_session, heavy_line, light_line)

    # Heavy line: one successful attempt -> the engine should recommend increasing.
    _completed_prescription(
        db_session,
        week_id=week.id,
        line_id=heavy_line.id,
        exercise_id=exercise.id,
        weight=HEAVY_WEIGHT,
        reps=TARGET_REPS,
    )
    heavy_current = _current_prescription(
        db_session,
        week_id=week.id,
        line_id=heavy_line.id,
        exercise_id=exercise.id,
        weight=HEAVY_WEIGHT,
    )

    # Light line: three consecutive failures -> the engine should recommend a
    # deload. If the two lines' histories were still merged (today's bug), the
    # heavy line's single success would reset this line's failure count to zero.
    for _ in range(3):
        _completed_prescription(
            db_session,
            week_id=week.id,
            line_id=light_line.id,
            exercise_id=exercise.id,
            weight=LIGHT_WEIGHT,
            reps=TARGET_REPS - 1,
        )
    light_current = _current_prescription(
        db_session,
        week_id=week.id,
        line_id=light_line.id,
        exercise_id=exercise.id,
        weight=LIGHT_WEIGHT,
    )

    heavy_recommendation = progression_service.get_recommendation_for_prescription(
        db_session, user_id=user.id, prescription_id=heavy_current.id
    )
    light_recommendation = progression_service.get_recommendation_for_prescription(
        db_session, user_id=user.id, prescription_id=light_current.id
    )

    assert heavy_recommendation.action == "increase"
    assert heavy_recommendation.recommended_weight == HEAVY_WEIGHT + INCREMENT
    assert heavy_recommendation.consecutive_failures == 0

    assert light_recommendation.action == "deload"
    assert light_recommendation.consecutive_failures == 3


def test_renaming_a_lines_label_does_not_change_its_recommendation(db_session):
    user, program, week, exercise = _build_program(db_session)
    line = make_progression_line(
        program_id=program.id, exercise_id=exercise.id, is_default=True
    )
    _persist(db_session, line)
    for _ in range(3):
        _completed_prescription(
            db_session,
            week_id=week.id,
            line_id=line.id,
            exercise_id=exercise.id,
            weight=HEAVY_WEIGHT,
            reps=TARGET_REPS - 1,
        )
    current = _current_prescription(
        db_session,
        week_id=week.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=HEAVY_WEIGHT,
    )

    before_rename = progression_service.get_recommendation_for_prescription(
        db_session, user_id=user.id, prescription_id=current.id
    )
    progression_lines_service.rename_progression_line(
        db_session, user_id=user.id, line_id=line.id, label="Renamed Squats"
    )
    after_rename = progression_service.get_recommendation_for_prescription(
        db_session, user_id=user.id, prescription_id=current.id
    )

    assert after_rename == before_rename

"""Integration tests for `training_weeks_service.generate_next_training_week` through
the real repositories and the real progression engine (TRAIN-25) — per CLAUDE.md's
"do not mock the progression engine", and because the weight rule (recommended weight
vs. verbatim fallback) is the load-bearing behaviour this ticket adds.

Real DB, real repositories, real engine — nothing here is mocked.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from app.models.enums import ProgressionType
from app.models.exercise_performance import ExercisePerformance
from app.models.exercise_prescription import ExercisePrescription
from app.models.progression_line import ProgressionLine
from app.models.workout_session import WorkoutSession
from app.schemas.training_weeks import TrainingWeekGenerateRequest
from app.services import training_weeks as training_weeks_service
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
STARTING_WEIGHT = 100.0
INCREMENT = 2.5
PERCENTAGE = 0.05
DELOAD_PERCENTAGE = 0.10
FAILURE_THRESHOLD = 3


def _persist(session, *objs):
    for obj in objs:
        session.add(obj)
    session.flush()


def _build_program(session, *, user_id=None, **program_overrides):
    user = make_profile() if user_id is None else None
    if user is not None:
        _persist(session, user)
        user_id = user.id
    exercise = make_exercise(created_by_user_id=user_id)
    _persist(session, exercise)
    program_fields = {
        "default_progression_type": ProgressionType.FIXED_INCREMENT,
        "default_progression_params": {"increment": INCREMENT},
    }
    program_fields.update(program_overrides)
    program = make_program(user_id=user_id, **program_fields)
    _persist(session, program)
    return user_id, program, exercise


def _completed_session_with_prescription(
    session, *, week_id, line_id, exercise_id, weight, reps, days_ago=1
):
    workout_session = make_workout_session(
        week_id=week_id,
        completed_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
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
        prescription_id=prescription.id, actual_reps=reps, actual_weight=weight
    )
    _persist(session, performance)
    return prescription


def _source_week_with_prescription(
    session, *, program_id, line_id, exercise_id, weight, week_number=2, **overrides
):
    source_week = make_training_week(program_id=program_id, week_number=week_number)
    _persist(session, source_week)
    workout_session = make_workout_session(week_id=source_week.id)
    _persist(session, workout_session)
    prescription = make_exercise_prescription(
        workout_session_id=workout_session.id,
        exercise_id=exercise_id,
        progression_line_id=line_id,
        target_sets=TARGET_SETS,
        target_reps=TARGET_REPS,
        target_weight=weight,
        **overrides,
    )
    _persist(session, prescription)
    return source_week, workout_session, prescription


def _generated_prescriptions(session, generated_week_id):
    session_ids = [
        s.id
        for s in session.exec(
            select(WorkoutSession).where(WorkoutSession.week_id == generated_week_id)
        ).all()
    ]
    return list(
        session.exec(
            select(ExercisePrescription).where(
                ExercisePrescription.workout_session_id.in_(session_ids)
            )
        ).all()
    )


def test_fixed_increment_success_uses_engine_recommended_weight(db_session):
    user_id, program, exercise = _build_program(db_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    history_week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, history_week)
    _completed_session_with_prescription(
        db_session,
        week_id=history_week.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
        reps=TARGET_REPS,
    )
    source_week, _, source_prescription = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
    )

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    [new_prescription] = _generated_prescriptions(db_session, generated.id)
    assert new_prescription.target_weight == STARTING_WEIGHT + INCREMENT
    assert (
        new_prescription.progression_line_id == source_prescription.progression_line_id
    )


def test_percentage_success_uses_engine_recommended_weight(db_session):
    user_id, program, exercise = _build_program(
        db_session,
        default_progression_type=ProgressionType.PERCENTAGE,
        default_progression_params={"percentage": PERCENTAGE},
    )
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    history_week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, history_week)
    _completed_session_with_prescription(
        db_session,
        week_id=history_week.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
        reps=TARGET_REPS,
    )
    source_week, _, _ = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
        progression_type=ProgressionType.PERCENTAGE,
    )

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    [new_prescription] = _generated_prescriptions(db_session, generated.id)
    expected = round((STARTING_WEIGHT * (1 + PERCENTAGE)) / INCREMENT) * INCREMENT
    assert new_prescription.target_weight == expected


def test_repeated_failures_reaching_threshold_uses_deloaded_weight(db_session):
    user_id, program, exercise = _build_program(db_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    history_week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, history_week)
    for day in range(FAILURE_THRESHOLD):
        _completed_session_with_prescription(
            db_session,
            week_id=history_week.id,
            line_id=line.id,
            exercise_id=exercise.id,
            weight=STARTING_WEIGHT,
            reps=TARGET_REPS - 1,
            days_ago=FAILURE_THRESHOLD - day,
        )
    source_week, _, _ = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
    )

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    [new_prescription] = _generated_prescriptions(db_session, generated.id)
    expected = (
        round((STARTING_WEIGHT * (1 - DELOAD_PERCENTAGE)) / INCREMENT) * INCREMENT
    )
    assert new_prescription.target_weight == expected


def test_manual_progression_falls_back_to_source_target_weight(db_session):
    user_id, program, exercise = _build_program(db_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    history_week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, history_week)
    _completed_session_with_prescription(
        db_session,
        week_id=history_week.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
        reps=TARGET_REPS,
    )
    source_week, _, source_prescription = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
        progression_type=ProgressionType.MANUAL,
    )

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    [new_prescription] = _generated_prescriptions(db_session, generated.id)
    assert new_prescription.target_weight == source_prescription.target_weight


def test_no_completed_history_falls_back_to_source_target_weight_verbatim(db_session):
    # Resolved design question 1: generating from a week with no completed
    # history anywhere on the line (no_data) is allowed and copies verbatim.
    user_id, program, exercise = _build_program(db_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    source_week, _, source_prescription = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
    )

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    [new_prescription] = _generated_prescriptions(db_session, generated.id)
    assert new_prescription.target_weight == source_prescription.target_weight


def test_missing_increment_configuration_falls_back_to_source_target_weight(
    db_session,
):
    user_id, program, exercise = _build_program(
        db_session,
        default_progression_type=ProgressionType.FIXED_INCREMENT,
        default_progression_params={},
    )
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    history_week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, history_week)
    _completed_session_with_prescription(
        db_session,
        week_id=history_week.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
        reps=TARGET_REPS,
    )
    source_week, _, source_prescription = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
    )

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    [new_prescription] = _generated_prescriptions(db_session, generated.id)
    assert new_prescription.target_weight == source_prescription.target_weight


def test_two_prescriptions_on_same_line_in_one_week_get_the_same_recommendation(
    db_session,
):
    # Resolved design question 2: StrongLifts-style Mon/Wed/Fri repeats of one
    # line within a still-incomplete week all pre-fill with the same number.
    user_id, program, exercise = _build_program(db_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    history_week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, history_week)
    _completed_session_with_prescription(
        db_session,
        week_id=history_week.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
        reps=TARGET_REPS,
    )
    source_week = make_training_week(program_id=program.id, week_number=2)
    _persist(db_session, source_week)
    monday = make_workout_session(
        week_id=source_week.id, day_name="Monday", order_index=0
    )
    friday = make_workout_session(
        week_id=source_week.id, day_name="Friday", order_index=1
    )
    _persist(db_session, monday, friday)
    monday_prescription = make_exercise_prescription(
        workout_session_id=monday.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        target_sets=TARGET_SETS,
        target_reps=TARGET_REPS,
        target_weight=STARTING_WEIGHT,
    )
    friday_prescription = make_exercise_prescription(
        workout_session_id=friday.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        target_sets=TARGET_SETS,
        target_reps=TARGET_REPS,
        target_weight=STARTING_WEIGHT,
    )
    _persist(db_session, monday_prescription, friday_prescription)

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    new_prescriptions = _generated_prescriptions(db_session, generated.id)
    assert len(new_prescriptions) == 2
    assert {p.target_weight for p in new_prescriptions} == {STARTING_WEIGHT + INCREMENT}


def test_no_new_progression_lines_are_created(db_session):
    user_id, program, exercise = _build_program(db_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    source_week, _, _ = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
    )
    lines_before = db_session.exec(
        select(ProgressionLine).where(ProgressionLine.program_id == program.id)
    ).all()

    training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    lines_after = db_session.exec(
        select(ProgressionLine).where(ProgressionLine.program_id == program.id)
    ).all()
    assert len(lines_after) == len(lines_before)


def test_week_number_is_max_plus_one_and_name_is_null_by_default(db_session):
    user_id, program, exercise = _build_program(db_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    first_week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, first_week)
    source_week, _, _ = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
        week_number=3,
    )

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    assert generated.week_number == 4
    assert generated.name is None


def test_name_is_honoured_when_supplied(db_session):
    user_id, program, exercise = _build_program(db_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    source_week, _, _ = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
    )

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(name="Deload Week"),
    )

    assert generated.name == "Deload Week"


def test_generating_from_an_empty_week_produces_an_empty_week(db_session):
    user_id, program, _ = _build_program(db_session)
    empty_week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, empty_week)

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=empty_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    assert generated.id is not None
    assert _generated_prescriptions(db_session, generated.id) == []


def test_generating_never_copies_performances_into_the_new_week(db_session):
    user_id, program, exercise = _build_program(db_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    history_week = make_training_week(program_id=program.id, week_number=1)
    _persist(db_session, history_week)
    _completed_session_with_prescription(
        db_session,
        week_id=history_week.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
        reps=TARGET_REPS,
    )
    source_week, _, _ = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
    )

    generated = training_weeks_service.generate_next_training_week(
        db_session,
        user_id=user_id,
        week_id=source_week.id,
        payload=TrainingWeekGenerateRequest(),
    )

    [new_prescription] = _generated_prescriptions(db_session, generated.id)
    performances = db_session.exec(
        select(ExercisePerformance).where(
            ExercisePerformance.prescription_id == new_prescription.id
        )
    ).all()
    assert performances == []


def test_generate_next_training_week_for_another_users_week_raises_access_denied(
    db_session,
):
    owner_id, program, exercise = _build_program(db_session)
    other_user = make_profile()
    _persist(db_session, other_user)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)
    source_week, _, _ = _source_week_with_prescription(
        db_session,
        program_id=program.id,
        line_id=line.id,
        exercise_id=exercise.id,
        weight=STARTING_WEIGHT,
    )

    with pytest.raises(training_weeks_service.TrainingWeekAccessDeniedError):
        training_weeks_service.generate_next_training_week(
            db_session,
            user_id=other_user.id,
            week_id=source_week.id,
            payload=TrainingWeekGenerateRequest(),
        )

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.exercise_performance import ExercisePerformance
from app.models.exercise_prescription import ExercisePrescription
from app.models.workout_session import WorkoutSession
from app.repositories import training_weeks as training_weeks_repo
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


def _build_source_tree(session):
    """A source week with two sessions, each carrying a prescription on its own
    progression line — enough for the session-id map to be exercised with more
    than one entry (a copy that collapsed everything onto the first session would
    otherwise pass unnoticed).
    """
    user = make_profile()
    exercise = make_exercise(created_by_user_id=user.id)
    _persist(session, user, exercise)
    program = make_program(user_id=user.id)
    _persist(session, program)
    week = make_training_week(program_id=program.id, week_number=1)
    _persist(session, week)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(session, line)

    monday = make_workout_session(
        week_id=week.id, day_name="Monday", order_index=0, notes="felt heavy"
    )
    wednesday = make_workout_session(
        week_id=week.id, day_name="Wednesday", order_index=1
    )
    _persist(session, monday, wednesday)

    monday_prescription = make_exercise_prescription(
        workout_session_id=monday.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        order_index=0,
        target_weight=100.0,
        progression_params={"increment": 2.5},
        notes="pause squats",
    )
    wednesday_prescription = make_exercise_prescription(
        workout_session_id=wednesday.id,
        exercise_id=exercise.id,
        progression_line_id=line.id,
        order_index=0,
        target_weight=60.0,
    )
    _persist(session, monday_prescription, wednesday_prescription)
    performance = make_exercise_performance(prescription_id=monday_prescription.id)
    _persist(session, performance)

    return program, [monday, wednesday], [monday_prescription, wednesday_prescription]


def test_create_week_from_source_copies_session_and_prescription_structure(db_session):
    program, source_sessions, source_prescriptions = _build_source_tree(db_session)
    target_weights = {
        source_prescriptions[0].id: 102.5,
        source_prescriptions[1].id: 62.5,
    }

    new_week = training_weeks_repo.create_week_from_source(
        db_session,
        program_id=program.id,
        week_number=2,
        name="Week 2",
        source_sessions=source_sessions,
        source_prescriptions=source_prescriptions,
        target_weight_by_prescription_id=target_weights,
    )

    assert new_week.week_number == 2
    assert new_week.name == "Week 2"
    new_sessions = db_session.exec(
        select(WorkoutSession)
        .where(WorkoutSession.week_id == new_week.id)
        .order_by(WorkoutSession.order_index)
    ).all()
    assert [s.day_name for s in new_sessions] == ["Monday", "Wednesday"]
    assert {s.notes for s in new_sessions} == {None}
    assert {s.started_at for s in new_sessions} == {None}
    assert {s.completed_at for s in new_sessions} == {None}


def test_create_week_from_source_uses_resolved_target_weights_and_keeps_line_ids(
    db_session,
):
    program, source_sessions, source_prescriptions = _build_source_tree(db_session)
    monday_source, wednesday_source = source_prescriptions
    target_weights = {
        monday_source.id: 102.5,
        wednesday_source.id: 62.5,
    }

    new_week = training_weeks_repo.create_week_from_source(
        db_session,
        program_id=program.id,
        week_number=2,
        name=None,
        source_sessions=source_sessions,
        source_prescriptions=source_prescriptions,
        target_weight_by_prescription_id=target_weights,
    )

    new_sessions_by_day_name = {
        session.day_name: session
        for session in db_session.exec(
            select(WorkoutSession).where(WorkoutSession.week_id == new_week.id)
        ).all()
    }

    def _prescriptions_for(day_name: str) -> list[ExercisePrescription]:
        return list(
            db_session.exec(
                select(ExercisePrescription).where(
                    ExercisePrescription.workout_session_id
                    == new_sessions_by_day_name[day_name].id
                )
            ).all()
        )

    # Directly pins the session-id map (`zip(source_sessions, new_sessions)`) rather
    # than inferring pairing from `notes`/target-weight alone — a bug that collapsed
    # every new prescription onto `new_sessions[0]` would still pass a check that
    # only compared the flattened sets across both sessions.
    [monday_new] = _prescriptions_for("Monday")
    [wednesday_new] = _prescriptions_for("Wednesday")

    assert monday_new.notes == "pause squats"
    assert monday_new.target_weight == 102.5
    assert monday_new.progression_line_id == monday_source.progression_line_id

    assert wednesday_new.notes is None
    assert wednesday_new.target_weight == 62.5
    assert wednesday_new.progression_line_id == wednesday_source.progression_line_id


def test_create_week_from_source_never_copies_performances(db_session):
    program, source_sessions, source_prescriptions = _build_source_tree(db_session)

    new_week = training_weeks_repo.create_week_from_source(
        db_session,
        program_id=program.id,
        week_number=2,
        name=None,
        source_sessions=source_sessions,
        source_prescriptions=source_prescriptions,
        target_weight_by_prescription_id={
            p.id: p.target_weight for p in source_prescriptions
        },
    )

    new_sessions = db_session.exec(
        select(WorkoutSession).where(WorkoutSession.week_id == new_week.id)
    ).all()
    new_prescriptions = db_session.exec(
        select(ExercisePrescription).where(
            ExercisePrescription.workout_session_id.in_([s.id for s in new_sessions])
        )
    ).all()
    performances = db_session.exec(
        select(ExercisePerformance).where(
            ExercisePerformance.prescription_id.in_([p.id for p in new_prescriptions])
        )
    ).all()

    assert performances == []


def test_create_week_from_source_shallow_copies_progression_params(db_session):
    program, source_sessions, source_prescriptions = _build_source_tree(db_session)
    monday_source = source_prescriptions[0]

    new_week = training_weeks_repo.create_week_from_source(
        db_session,
        program_id=program.id,
        week_number=2,
        name=None,
        source_sessions=source_sessions,
        source_prescriptions=source_prescriptions,
        target_weight_by_prescription_id={
            p.id: p.target_weight for p in source_prescriptions
        },
    )

    new_sessions = db_session.exec(
        select(WorkoutSession).where(WorkoutSession.week_id == new_week.id)
    ).all()
    new_prescriptions = db_session.exec(
        select(ExercisePrescription).where(
            ExercisePrescription.workout_session_id.in_([s.id for s in new_sessions])
        )
    ).all()
    monday_new = next(p for p in new_prescriptions if p.notes == "pause squats")

    monday_new.progression_params["increment"] = 999
    assert monday_source.progression_params["increment"] == 2.5


def test_create_week_from_source_with_no_sessions_produces_empty_week(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id)
    _persist(db_session, program)

    new_week = training_weeks_repo.create_week_from_source(
        db_session,
        program_id=program.id,
        week_number=1,
        name=None,
        source_sessions=[],
        source_prescriptions=[],
        target_weight_by_prescription_id={},
    )

    assert new_week.id is not None
    remaining_sessions = db_session.exec(
        select(WorkoutSession).where(WorkoutSession.week_id == new_week.id)
    ).all()
    assert remaining_sessions == []

import pytest

from app.repositories import progression_lines as progression_lines_repo
from tests.factories import (
    make_exercise,
    make_profile,
    make_program,
    make_progression_line,
)

pytestmark = pytest.mark.integration


def _persist(session, *objs):
    for obj in objs:
        session.add(obj)
    session.flush()


def _make_program_and_exercise(session):
    user = make_profile()
    exercise = make_exercise(created_by_user_id=user.id)
    _persist(session, user, exercise)
    program = make_program(user_id=user.id)
    _persist(session, program)
    return user, program, exercise


def test_list_progression_lines_orders_default_first_then_by_id(db_session):
    _, program, exercise = _make_program_and_exercise(db_session)
    explicit_line = make_progression_line(
        program_id=program.id, exercise_id=exercise.id, is_default=False, label="Light"
    )
    _persist(db_session, explicit_line)
    default_line = make_progression_line(
        program_id=program.id, exercise_id=exercise.id, is_default=True
    )
    _persist(db_session, default_line)

    lines = progression_lines_repo.list_progression_lines(
        db_session, program_id=program.id, exercise_id=exercise.id
    )

    assert [line.id for line in lines] == [default_line.id, explicit_line.id]


def test_get_default_progression_line_returns_none_when_only_explicit_lines_exist(
    db_session,
):
    _, program, exercise = _make_program_and_exercise(db_session)
    _persist(
        db_session,
        make_progression_line(
            program_id=program.id,
            exercise_id=exercise.id,
            is_default=False,
            label="Light",
        ),
    )

    assert (
        progression_lines_repo.get_default_progression_line(
            db_session, program_id=program.id, exercise_id=exercise.id
        )
        is None
    )


def test_get_progression_line_with_owner_returns_the_owning_programs_user_id(
    db_session,
):
    user, program, exercise = _make_program_and_exercise(db_session)
    line = make_progression_line(program_id=program.id, exercise_id=exercise.id)
    _persist(db_session, line)

    result = progression_lines_repo.get_progression_line_with_owner(db_session, line.id)

    assert result is not None
    fetched_line, owner_user_id = result
    assert fetched_line.id == line.id
    assert owner_user_id == user.id


def test_update_progression_line_label_does_not_change_is_default(db_session):
    _, program, exercise = _make_program_and_exercise(db_session)
    line = make_progression_line(
        program_id=program.id, exercise_id=exercise.id, is_default=True, label=None
    )
    _persist(db_session, line)

    updated = progression_lines_repo.update_progression_line_label(
        db_session, line, "Renamed"
    )

    assert updated.label == "Renamed"
    assert updated.is_default is True

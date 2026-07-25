import pytest
from sqlmodel import select

from app.models.enums import WeightUnit
from app.models.exercise import Exercise
from app.models.exercise_prescription import ExercisePrescription
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession
from app.repositories import programs as programs_repo
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


def test_create_and_get_program(db_session):
    user = make_profile()
    _persist(db_session, user)

    program = programs_repo.create_program(
        db_session,
        user_id=user.id,
        name="Texas Method",
        weight_unit=WeightUnit.LB,
    )
    fetched = programs_repo.get_program(db_session, program.id)
    assert fetched is not None
    assert fetched.name == "Texas Method"
    assert fetched.weight_unit == WeightUnit.LB


def test_list_and_active_program_scoped_to_user(db_session):
    user = make_profile()
    other = make_profile()
    _persist(db_session, user, other)

    active = make_program(user_id=user.id, name="Active", is_active=True)
    inactive = make_program(user_id=user.id, name="Old", is_active=False)
    foreign = make_program(user_id=other.id, name="Theirs", is_active=True)
    _persist(db_session, active, inactive, foreign)

    listed = programs_repo.list_programs_for_user(db_session, user_id=user.id)
    assert {p.name for p in listed} == {"Active", "Old"}

    found_active = programs_repo.get_active_program(db_session, user_id=user.id)
    assert found_active.name == "Active"


def test_update_program_applies_given_fields(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="Original")
    _persist(db_session, program)

    updated = programs_repo.update_program(db_session, program, name="Renamed")

    assert updated.name == "Renamed"
    refetched = programs_repo.get_program(db_session, program.id)
    assert refetched.name == "Renamed"


def test_update_program_with_disallowed_field_raises_value_error(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="Original")
    _persist(db_session, program)

    with pytest.raises(ValueError):
        programs_repo.update_program(db_session, program, user_id=user.id + 1)


def test_archive_program_sets_archived_at_and_clears_is_active(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="To Archive", is_active=True)
    _persist(db_session, program)

    programs_repo.archive_program(db_session, program)

    assert program.archived_at is not None
    assert program.is_active is False


def test_archive_program_is_idempotent_and_keeps_original_timestamp(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="To Archive")
    _persist(db_session, program)

    programs_repo.archive_program(db_session, program)
    first_archived_at = program.archived_at
    programs_repo.archive_program(db_session, program)

    assert program.archived_at == first_archived_at


def test_archived_program_still_fetchable_by_id(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="To Archive")
    _persist(db_session, program)

    programs_repo.archive_program(db_session, program)

    assert programs_repo.get_program(db_session, program.id) is not None


def test_archived_program_excluded_from_default_list_but_included_when_asked(
    db_session,
):
    user = make_profile()
    _persist(db_session, user)
    active = make_program(user_id=user.id, name="Active")
    archived = make_program(user_id=user.id, name="Archived")
    _persist(db_session, active, archived)
    programs_repo.archive_program(db_session, archived)

    default_listed = programs_repo.list_programs_for_user(db_session, user_id=user.id)
    assert {p.name for p in default_listed} == {"Active"}

    with_archived = programs_repo.list_programs_for_user(
        db_session, user_id=user.id, include_archived=True
    )
    assert {p.name for p in with_archived} == {"Active", "Archived"}


def test_archiving_the_active_program_clears_active_lookup(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="Was Active", is_active=True)
    _persist(db_session, program)

    programs_repo.archive_program(db_session, program)

    assert programs_repo.get_active_program(db_session, user_id=user.id) is None


def test_unarchive_program_clears_archived_at(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="Archived")
    _persist(db_session, program)
    programs_repo.archive_program(db_session, program)

    programs_repo.unarchive_program(db_session, program)

    assert program.archived_at is None


def test_unarchive_program_is_idempotent_on_a_non_archived_program(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="Never Archived")
    _persist(db_session, program)

    programs_repo.unarchive_program(db_session, program)

    assert program.archived_at is None


def test_unarchived_program_restored_to_default_list(db_session):
    user = make_profile()
    _persist(db_session, user)
    program = make_program(user_id=user.id, name="Roundtrip")
    _persist(db_session, program)
    programs_repo.archive_program(db_session, program)

    programs_repo.unarchive_program(db_session, program)

    listed = programs_repo.list_programs_for_user(db_session, user_id=user.id)
    assert {p.name for p in listed} == {"Roundtrip"}


def test_deactivate_other_active_programs_deactivates_only_same_user(db_session):
    user = make_profile()
    other = make_profile()
    _persist(db_session, user, other)

    active_one = make_program(user_id=user.id, name="Active One", is_active=True)
    active_two = make_program(user_id=user.id, name="Active Two", is_active=True)
    foreign_active = make_program(user_id=other.id, name="Theirs", is_active=True)
    _persist(db_session, active_one, active_two, foreign_active)

    programs_repo.deactivate_other_active_programs(db_session, user.id)
    db_session.flush()

    assert active_one.is_active is False
    assert active_two.is_active is False
    assert foreign_active.is_active is True


def test_deactivate_other_active_programs_clears_an_archived_program_left_active(
    db_session,
):
    # Self-healing case the migration backfill exists for: a program archived under
    # the old soft-delete mechanic could still have is_active=true. Now that
    # get_active_program/deactivate_other_active_programs no longer filter on
    # archived_at, deactivate_other_active_programs must still pick up and clear such
    # a row rather than leaving the "archived implies not active" invariant violated.
    user = make_profile()
    _persist(db_session, user)

    newly_activated = make_program(user_id=user.id, name="New", is_active=True)
    stale_archived_active = make_program(user_id=user.id, name="Stale", is_active=True)
    _persist(db_session, newly_activated, stale_archived_active)
    stale_archived_active.archived_at = stale_archived_active.created_at
    _persist(db_session, stale_archived_active)

    programs_repo.deactivate_other_active_programs(
        db_session, user.id, exclude_program_id=newly_activated.id
    )
    db_session.flush()

    assert stale_archived_active.is_active is False


def test_deactivate_other_active_programs_excludes_given_program_id(db_session):
    user = make_profile()
    _persist(db_session, user)

    newly_activated = make_program(user_id=user.id, name="New", is_active=True)
    previously_active = make_program(user_id=user.id, name="Old", is_active=True)
    _persist(db_session, newly_activated, previously_active)

    programs_repo.deactivate_other_active_programs(
        db_session, user.id, exclude_program_id=newly_activated.id
    )
    db_session.flush()

    assert newly_activated.is_active is True
    assert previously_active.is_active is False


def test_delete_program_cascades_to_full_tree_but_leaves_exercise_untouched(
    db_session,
):
    user = make_profile()
    exercise = make_exercise(created_by_user_id=user.id)
    _persist(db_session, user, exercise)

    program = make_program(user_id=user.id)
    _persist(db_session, program)
    week = make_training_week(program_id=program.id)
    _persist(db_session, week)
    session_day = make_workout_session(week_id=week.id)
    _persist(db_session, session_day)
    rx = make_exercise_prescription(
        workout_session_id=session_day.id, exercise_id=exercise.id
    )
    _persist(db_session, rx)

    programs_repo.delete_program(db_session, program)

    # The whole week -> session -> prescription tree is gone.
    assert db_session.exec(select(TrainingWeek)).all() == []
    assert db_session.exec(select(WorkoutSession)).all() == []
    assert db_session.exec(select(ExercisePrescription)).all() == []
    # The exercise itself survives: prescriptions reference it with
    # ondelete="RESTRICT" and no cascading relationship, since Exercise is an
    # independent entity never owned by a Program (see CLAUDE.md's Entity Lifecycle
    # Conventions).
    assert db_session.get(Exercise, exercise.id) is not None

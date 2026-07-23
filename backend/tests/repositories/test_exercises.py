import pytest

from app.models.enums import Equipment, MuscleGroup
from app.repositories import exercises as exercises_repo
from tests.factories import make_exercise, make_profile

pytestmark = pytest.mark.integration


def _persist(session, *objs):
    for obj in objs:
        session.add(obj)
    session.flush()


def test_list_exercises_includes_system_and_own_custom(db_session):
    user = make_profile()
    other = make_profile()
    _persist(db_session, user, other)

    mine = make_exercise(name="My Curl", created_by_user_id=user.id)
    theirs = make_exercise(name="Their Curl", created_by_user_id=other.id)
    _persist(db_session, mine, theirs)

    result = exercises_repo.list_exercises(db_session, user_id=user.id)
    names = {e.name for e in result}

    # Own custom exercise is visible; another user's is not.
    assert "My Curl" in names
    assert "Their Curl" not in names
    # Seeded system exercises (created_by_user_id IS NULL) are visible to everyone.
    assert "Squat" in names


def test_list_exercises_filters_by_muscle_group(db_session):
    user = make_profile()
    _persist(db_session, user)

    legs = make_exercise(
        name="Hack Squat",
        created_by_user_id=user.id,
        muscle_group=MuscleGroup.QUADS,
    )
    arms = make_exercise(
        name="Preacher Curl",
        created_by_user_id=user.id,
        muscle_group=MuscleGroup.BICEPS,
    )
    _persist(db_session, legs, arms)

    result = exercises_repo.list_exercises(
        db_session, user_id=user.id, muscle_group=MuscleGroup.BICEPS
    )
    names = {e.name for e in result}
    assert "Preacher Curl" in names
    assert "Hack Squat" not in names


def test_create_exercise_persists_custom(db_session):
    user = make_profile()
    _persist(db_session, user)

    created = exercises_repo.create_exercise(
        db_session,
        name="Zercher Squat",
        muscle_group=MuscleGroup.QUADS,
        equipment=Equipment.BARBELL,
        created_by_user_id=user.id,
    )
    assert created.id is not None
    assert exercises_repo.get_exercise(db_session, created.id).name == "Zercher Squat"


def test_duplicate_system_exercise_name_is_rejected(db_session):
    # The partial unique index forbids two system exercises sharing a name.
    dup = make_exercise(name="Squat", created_by_user_id=None)
    db_session.add(dup)
    with pytest.raises(Exception):  # IntegrityError surfaced on flush
        db_session.flush()

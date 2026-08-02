import pytest

from app.models.enums import Equipment, ExerciseCategory, MuscleGroup
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


def test_list_exercises_filters_by_search_case_insensitively(db_session):
    user = make_profile()
    _persist(db_session, user)

    sissy_squat = make_exercise(name="Sissy Squat", created_by_user_id=user.id)
    preacher = make_exercise(name="Preacher Curl", created_by_user_id=user.id)
    _persist(db_session, sissy_squat, preacher)

    result = exercises_repo.list_exercises(db_session, user_id=user.id, search="sissy")
    names = {e.name for e in result}
    assert "Sissy Squat" in names
    assert "Preacher Curl" not in names


def test_list_exercises_filters_by_category(db_session):
    user = make_profile()
    _persist(db_session, user)

    compound = make_exercise(
        name="Front Squat",
        created_by_user_id=user.id,
        category=ExerciseCategory.COMPOUND,
    )
    isolation = make_exercise(
        name="Leg Extension",
        created_by_user_id=user.id,
        category=ExerciseCategory.ISOLATION,
    )
    _persist(db_session, compound, isolation)

    result = exercises_repo.list_exercises(
        db_session, user_id=user.id, category=ExerciseCategory.ISOLATION
    )
    names = {e.name for e in result}
    assert "Leg Extension" in names
    assert "Front Squat" not in names


def test_find_visible_exercise_by_name_matches_case_insensitively(db_session):
    user = make_profile()
    _persist(db_session, user)
    _persist(db_session, make_exercise(name="Sissy Squat", created_by_user_id=user.id))

    found = exercises_repo.find_visible_exercise_by_name(
        db_session, user_id=user.id, name="  sissy squat  "
    )

    assert found is not None
    assert found.name == "Sissy Squat"


def test_find_visible_exercise_by_name_does_not_match_another_users_custom(db_session):
    user = make_profile()
    other = make_profile()
    _persist(db_session, user, other)
    _persist(db_session, make_exercise(name="Their Curl", created_by_user_id=other.id))

    found = exercises_repo.find_visible_exercise_by_name(
        db_session, user_id=user.id, name="Their Curl"
    )

    assert found is None


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


def test_duplicate_custom_exercise_name_for_same_user_is_rejected(db_session):
    # uq_exercise_user_name forbids one user from having two custom exercises with
    # the same name, case-insensitively — the DB-level backstop for the race the
    # service's check-then-act name lookup can't fully close on its own.
    user = make_profile()
    _persist(db_session, user)
    _persist(db_session, make_exercise(name="My Curl", created_by_user_id=user.id))

    dup = make_exercise(name="MY CURL", created_by_user_id=user.id)
    db_session.add(dup)
    with pytest.raises(Exception):  # IntegrityError surfaced on flush
        db_session.flush()


def test_duplicate_custom_exercise_name_across_users_is_allowed(db_session):
    # uq_exercise_user_name is scoped by created_by_user_id, so it must never
    # constrain one user's custom exercise names against another's.
    user = make_profile()
    other = make_profile()
    _persist(db_session, user, other)
    _persist(db_session, make_exercise(name="My Curl", created_by_user_id=user.id))

    same_name_other_owner = make_exercise(name="My Curl", created_by_user_id=other.id)
    db_session.add(same_name_other_owner)
    db_session.flush()  # should not raise

    assert same_name_other_owner.id is not None

"""Unit tests for app.services.exercises.

The repository layer is external I/O, so it's mocked here — these tests exercise
search normalization and the duplicate-name rule that actually lives in the
service, not the database.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import Equipment, MuscleGroup
from app.schemas.exercises import ExerciseCreate
from app.services import exercises as exercises_service
from tests.factories import make_exercise

OWNER_ID = 1
OTHER_USER_ID = 2


def _create_payload(**overrides) -> ExerciseCreate:
    data = {
        "name": "Bulgarian Split Squat",
        "muscle_group": MuscleGroup.QUADS,
        "equipment": Equipment.DUMBBELL,
    }
    data.update(overrides)
    return ExerciseCreate(**data)


def test_list_exercises_passes_filters_through_to_the_repo(monkeypatch):
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(exercises_service.exercises_repo, "list_exercises", list_mock)
    session = MagicMock()

    exercises_service.list_exercises(
        session,
        user_id=OWNER_ID,
        search="curl",
        muscle_group=MuscleGroup.BICEPS,
        category=None,
    )

    list_mock.assert_called_once_with(
        session,
        OWNER_ID,
        muscle_group=MuscleGroup.BICEPS,
        search="curl",
        category=None,
    )


def test_list_exercises_with_whitespace_only_search_treats_it_as_no_filter(
    monkeypatch,
):
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(exercises_service.exercises_repo, "list_exercises", list_mock)
    session = MagicMock()

    exercises_service.list_exercises(session, user_id=OWNER_ID, search="   ")

    _, called_kwargs = list_mock.call_args
    assert called_kwargs["search"] is None


def test_list_exercises_strips_surrounding_whitespace_from_search(monkeypatch):
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(exercises_service.exercises_repo, "list_exercises", list_mock)
    session = MagicMock()

    exercises_service.list_exercises(session, user_id=OWNER_ID, search="  squat  ")

    _, called_kwargs = list_mock.call_args
    assert called_kwargs["search"] == "squat"


def test_create_custom_exercise_forces_ownership_onto_the_caller(monkeypatch):
    monkeypatch.setattr(
        exercises_service.exercises_repo,
        "find_visible_exercise_by_name",
        lambda *a, **k: None,
    )
    create_mock = MagicMock(return_value=make_exercise())
    monkeypatch.setattr(
        exercises_service.exercises_repo, "create_exercise", create_mock
    )
    session = MagicMock()

    exercises_service.create_custom_exercise(
        session, user_id=OWNER_ID, payload=_create_payload()
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["created_by_user_id"] == OWNER_ID


def test_create_custom_exercise_colliding_with_a_system_exercise_raises_duplicate(
    monkeypatch,
):
    existing = make_exercise(name="Squat", created_by_user_id=None)
    monkeypatch.setattr(
        exercises_service.exercises_repo,
        "find_visible_exercise_by_name",
        lambda *a, **k: existing,
    )
    create_mock = MagicMock()
    monkeypatch.setattr(
        exercises_service.exercises_repo, "create_exercise", create_mock
    )

    with pytest.raises(exercises_service.DuplicateExerciseNameError):
        exercises_service.create_custom_exercise(
            MagicMock(),
            user_id=OWNER_ID,
            payload=_create_payload(name="squat"),
        )
    create_mock.assert_not_called()


def test_create_custom_exercise_colliding_with_the_callers_own_custom_raises_duplicate(
    monkeypatch,
):
    existing = make_exercise(name="My Curl", created_by_user_id=OWNER_ID)
    monkeypatch.setattr(
        exercises_service.exercises_repo,
        "find_visible_exercise_by_name",
        lambda *a, **k: existing,
    )
    create_mock = MagicMock()
    monkeypatch.setattr(
        exercises_service.exercises_repo, "create_exercise", create_mock
    )

    with pytest.raises(exercises_service.DuplicateExerciseNameError):
        exercises_service.create_custom_exercise(
            MagicMock(),
            user_id=OWNER_ID,
            payload=_create_payload(name="MY CURL"),
        )
    create_mock.assert_not_called()


def test_create_custom_exercise_matching_another_users_custom_is_not_a_collision(
    monkeypatch,
):
    # find_visible_exercise_by_name is per-caller scoped in the repo, so a repo
    # that correctly excludes another user's custom returns None here — the
    # service must go ahead and create it rather than treating a same name
    # under a different owner as a duplicate.
    monkeypatch.setattr(
        exercises_service.exercises_repo,
        "find_visible_exercise_by_name",
        lambda *a, **k: None,
    )
    created = make_exercise(name="Their Curl", created_by_user_id=OWNER_ID)
    create_mock = MagicMock(return_value=created)
    monkeypatch.setattr(
        exercises_service.exercises_repo, "create_exercise", create_mock
    )

    result = exercises_service.create_custom_exercise(
        MagicMock(),
        user_id=OWNER_ID,
        payload=_create_payload(name="Their Curl"),
    )

    assert result is created
    create_mock.assert_called_once()


def test_create_custom_exercise_raises_duplicate_on_race_lost_at_commit(monkeypatch):
    # Simulates two concurrent requests both passing the name check before either
    # commits: the repo's insert then hits uq_exercise_user_name and raises
    # IntegrityError, which the service must translate to the same public error
    # the pre-check path raises, and must roll back the session.
    monkeypatch.setattr(
        exercises_service.exercises_repo,
        "find_visible_exercise_by_name",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        exercises_service.exercises_repo,
        "create_exercise",
        MagicMock(side_effect=IntegrityError("INSERT", {}, Exception("dup"))),
    )
    session = MagicMock()

    with pytest.raises(exercises_service.DuplicateExerciseNameError):
        exercises_service.create_custom_exercise(
            session, user_id=OWNER_ID, payload=_create_payload()
        )
    session.rollback.assert_called_once()

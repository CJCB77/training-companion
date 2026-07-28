"""Route-level tests for /exercises.

The service layer is mocked here — business logic (search normalization,
duplicate-name detection) is covered in tests/services/test_exercises.py. These
tests only verify HTTP wiring: status codes, auth enforcement, response shape,
and query-param passthrough.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.models.enums import Equipment, MuscleGroup
from app.services import exercises as exercises_service
from tests.factories import make_exercise, make_profile

EXERCISE_ID = 7


def _fake_session():
    # The service layer is mocked in every test here, so the session itself is
    # never used to query anything — this just satisfies the route's Depends
    # without needing a real DATABASE_URL/engine (empty in CI).
    yield MagicMock()


@pytest.fixture
def current_user():
    user = make_profile()
    user.id = 1
    return user


@pytest.fixture
def authenticated_client(current_user):
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session] = _fake_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_session, None)


def _exercise_double(*, created_by_user_id: int | None = None) -> object:
    exercise = make_exercise(name="Leg Press", created_by_user_id=created_by_user_id)
    exercise.id = EXERCISE_ID
    exercise.created_at = datetime.now(timezone.utc)
    exercise.updated_at = datetime.now(timezone.utc)
    return exercise


def _create_payload(**overrides) -> dict:
    payload = {
        "name": "Bulgarian Split Squat",
        "muscle_group": MuscleGroup.QUADS.value,
        "equipment": Equipment.DUMBBELL.value,
    }
    payload.update(overrides)
    return payload


def test_list_exercises_without_auth_returns_401(client):
    response = client.get("/exercises")

    assert response.status_code == 401


def test_create_exercise_without_auth_returns_401(client):
    response = client.post("/exercises", json=_create_payload())

    assert response.status_code == 401


def test_list_exercises_returns_200_with_the_services_result(
    authenticated_client, monkeypatch
):
    exercises = [_exercise_double()]
    monkeypatch.setattr(exercises_service, "list_exercises", lambda *a, **k: exercises)

    response = authenticated_client.get("/exercises")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == EXERCISE_ID


def test_list_exercises_passes_query_params_through_to_the_service(
    authenticated_client, monkeypatch
):
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(exercises_service, "list_exercises", list_mock)

    response = authenticated_client.get(
        "/exercises?search=curl&muscle_group=biceps&category=isolation"
    )

    assert response.status_code == 200
    _, called_kwargs = list_mock.call_args
    assert called_kwargs["search"] == "curl"
    assert called_kwargs["muscle_group"] == MuscleGroup.BICEPS
    assert called_kwargs["category"].value == "isolation"


def test_list_exercises_with_invalid_muscle_group_returns_422(authenticated_client):
    response = authenticated_client.get("/exercises?muscle_group=not-a-real-group")

    assert response.status_code == 422


def test_create_exercise_returns_201_and_created_exercise(
    authenticated_client, current_user, monkeypatch
):
    created = _exercise_double(created_by_user_id=current_user.id)
    monkeypatch.setattr(
        exercises_service, "create_custom_exercise", lambda *a, **k: created
    )

    response = authenticated_client.post("/exercises", json=_create_payload())

    assert response.status_code == 201
    assert response.json()["name"] == "Leg Press"
    assert response.json()["is_custom"] is True


def test_create_exercise_with_duplicate_name_returns_409(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercises_service.DuplicateExerciseNameError("Bulgarian Split Squat")

    monkeypatch.setattr(exercises_service, "create_custom_exercise", _raise)

    response = authenticated_client.post("/exercises", json=_create_payload())

    assert response.status_code == 409


def test_create_exercise_with_blank_name_returns_422(authenticated_client):
    response = authenticated_client.post("/exercises", json=_create_payload(name="   "))

    assert response.status_code == 422

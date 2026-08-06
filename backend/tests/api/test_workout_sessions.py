"""Route-level tests for workout-session endpoints.

The service layer is mocked here — business logic (ownership, order_index
assignment) is covered in tests/services/test_workout_sessions.py. These tests
only verify HTTP wiring: status codes, auth enforcement, response shape, and the
not-found/access-denied 404 masking (both the session's own and its parent
training week's).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.services import training_weeks as training_weeks_service
from app.services import workout_sessions as workout_sessions_service
from tests.factories import make_profile, make_workout_session

WEEK_ID = 7
SESSION_ID = 42


def _fake_session():
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


def _session_read_double(**overrides) -> object:
    workout_session = make_workout_session(week_id=WEEK_ID, **overrides)
    workout_session.id = SESSION_ID
    workout_session.created_at = datetime.now(timezone.utc)
    workout_session.updated_at = datetime.now(timezone.utc)
    return workout_session


def test_create_workout_session_without_auth_returns_401(client):
    response = client.post(
        f"/training-weeks/{WEEK_ID}/workout-sessions", json={"day_name": "Day A"}
    )

    assert response.status_code == 401


def test_create_workout_session_returns_201_and_created_session(
    authenticated_client, monkeypatch
):
    created = _session_read_double()
    monkeypatch.setattr(
        workout_sessions_service,
        "create_workout_session_for_week",
        lambda *a, **k: created,
    )

    response = authenticated_client.post(
        f"/training-weeks/{WEEK_ID}/workout-sessions", json={"day_name": "Day A"}
    )

    assert response.status_code == 201
    assert response.json()["id"] == SESSION_ID


def test_create_workout_session_for_unowned_week_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise training_weeks_service.TrainingWeekAccessDeniedError(WEEK_ID)

    monkeypatch.setattr(
        workout_sessions_service, "create_workout_session_for_week", _raise
    )

    response = authenticated_client.post(
        f"/training-weeks/{WEEK_ID}/workout-sessions", json={"day_name": "Day A"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Training week not found"


def test_list_workout_sessions_returns_only_the_services_result(
    authenticated_client, monkeypatch
):
    sessions = [_session_read_double()]
    monkeypatch.setattr(
        workout_sessions_service, "list_workout_sessions", lambda *a, **k: sessions
    )

    response = authenticated_client.get(f"/training-weeks/{WEEK_ID}/workout-sessions")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_workout_sessions_for_unowned_week_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise training_weeks_service.TrainingWeekNotFoundError(WEEK_ID)

    monkeypatch.setattr(workout_sessions_service, "list_workout_sessions", _raise)

    response = authenticated_client.get(f"/training-weeks/{WEEK_ID}/workout-sessions")

    assert response.status_code == 404


def test_get_workout_session_owned_by_caller_returns_200(
    authenticated_client, monkeypatch
):
    workout_session = _session_read_double()
    monkeypatch.setattr(
        workout_sessions_service,
        "get_owned_workout_session",
        lambda *a, **k: workout_session,
    )

    response = authenticated_client.get(f"/workout-sessions/{SESSION_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == SESSION_ID


def test_get_workout_session_owned_by_another_user_returns_404(
    authenticated_client, monkeypatch
):
    # Access-denied must be indistinguishable from not-found to the caller.
    def _raise(*args, **kwargs):
        raise workout_sessions_service.WorkoutSessionAccessDeniedError(SESSION_ID)

    monkeypatch.setattr(workout_sessions_service, "get_owned_workout_session", _raise)

    response = authenticated_client.get(f"/workout-sessions/{SESSION_ID}")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Workout session not found"


def test_update_workout_session_owned_by_caller_returns_200(
    authenticated_client, monkeypatch
):
    updated = _session_read_double()
    monkeypatch.setattr(
        workout_sessions_service, "update_workout_session", lambda *a, **k: updated
    )

    response = authenticated_client.put(
        f"/workout-sessions/{SESSION_ID}", json={"order_index": 2}
    )

    assert response.status_code == 200


def test_update_workout_session_not_found_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise workout_sessions_service.WorkoutSessionNotFoundError(SESSION_ID)

    monkeypatch.setattr(workout_sessions_service, "update_workout_session", _raise)

    response = authenticated_client.put(
        f"/workout-sessions/{SESSION_ID}", json={"order_index": 2}
    )

    assert response.status_code == 404


def test_delete_workout_session_owned_by_caller_returns_204(
    authenticated_client, monkeypatch
):
    delete_mock = MagicMock(return_value=None)
    monkeypatch.setattr(workout_sessions_service, "delete_workout_session", delete_mock)

    response = authenticated_client.delete(f"/workout-sessions/{SESSION_ID}")

    assert response.status_code == 204
    delete_mock.assert_called_once()


def test_delete_workout_session_access_denied_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise workout_sessions_service.WorkoutSessionAccessDeniedError(SESSION_ID)

    monkeypatch.setattr(workout_sessions_service, "delete_workout_session", _raise)

    response = authenticated_client.delete(f"/workout-sessions/{SESSION_ID}")

    assert response.status_code == 404


def test_update_workout_session_with_null_day_name_returns_422(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise workout_sessions_service.InvalidWorkoutSessionUpdateError(
            "day_name cannot be null"
        )

    monkeypatch.setattr(workout_sessions_service, "update_workout_session", _raise)

    response = authenticated_client.put(
        f"/workout-sessions/{SESSION_ID}", json={"day_name": None}
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "day_name cannot be null"


def test_start_workout_session_owned_by_caller_returns_200(
    authenticated_client, monkeypatch
):
    started = _session_read_double()
    monkeypatch.setattr(
        workout_sessions_service, "start_workout_session", lambda *a, **k: started
    )

    response = authenticated_client.post(f"/workout-sessions/{SESSION_ID}/start")

    assert response.status_code == 200
    assert response.json()["id"] == SESSION_ID


def test_start_workout_session_for_other_users_session_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise workout_sessions_service.WorkoutSessionAccessDeniedError(SESSION_ID)

    monkeypatch.setattr(workout_sessions_service, "start_workout_session", _raise)

    response = authenticated_client.post(f"/workout-sessions/{SESSION_ID}/start")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Workout session not found"


def test_complete_workout_session_owned_by_caller_returns_200(
    authenticated_client, monkeypatch
):
    completed = _session_read_double()
    monkeypatch.setattr(
        workout_sessions_service, "complete_workout_session", lambda *a, **k: completed
    )

    response = authenticated_client.post(f"/workout-sessions/{SESSION_ID}/complete")

    assert response.status_code == 200
    assert response.json()["id"] == SESSION_ID


def test_complete_workout_session_for_other_users_session_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise workout_sessions_service.WorkoutSessionAccessDeniedError(SESSION_ID)

    monkeypatch.setattr(workout_sessions_service, "complete_workout_session", _raise)

    response = authenticated_client.post(f"/workout-sessions/{SESSION_ID}/complete")

    assert response.status_code == 404

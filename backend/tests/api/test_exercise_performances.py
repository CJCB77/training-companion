"""Route-level tests for exercise-performance endpoints.

The service layer is mocked here — business logic (ownership, set_number
assignment) is covered in tests/services/test_exercise_performances.py. These
tests only verify HTTP wiring: status codes, auth enforcement, response shape,
and the not-found/access-denied 404 masking (the performance's own, its parent
prescription's, and its parent session's).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.models.enums import SetCompletionState
from app.services import exercise_performances as exercise_performances_service
from app.services import exercise_prescriptions as exercise_prescriptions_service
from app.services import workout_sessions as workout_sessions_service
from tests.factories import make_exercise_performance, make_profile

PRESCRIPTION_ID = 10
SESSION_ID = 20
PERFORMANCE_ID = 42


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


def _performance_read_double(**overrides) -> object:
    performance = make_exercise_performance(
        prescription_id=PRESCRIPTION_ID, **overrides
    )
    performance.id = PERFORMANCE_ID
    performance.created_at = datetime.now(timezone.utc)
    performance.updated_at = datetime.now(timezone.utc)
    return performance


def _create_payload(**overrides) -> dict:
    payload = {"actual_reps": 5, "completion_state": SetCompletionState.COMPLETED}
    payload.update(overrides)
    return payload


def test_create_exercise_performance_without_auth_returns_401(client):
    response = client.post(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}/performances",
        json=_create_payload(),
    )

    assert response.status_code == 401


def test_create_exercise_performance_returns_201_and_created_performance(
    authenticated_client, monkeypatch
):
    created = _performance_read_double()
    monkeypatch.setattr(
        exercise_performances_service,
        "create_exercise_performance_for_prescription",
        lambda *a, **k: created,
    )

    response = authenticated_client.post(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}/performances",
        json=_create_payload(),
    )

    assert response.status_code == 201
    assert response.json()["id"] == PERFORMANCE_ID


def test_create_exercise_performance_for_unowned_prescription_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError(
            PRESCRIPTION_ID
        )

    monkeypatch.setattr(
        exercise_performances_service,
        "create_exercise_performance_for_prescription",
        _raise,
    )

    response = authenticated_client.post(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}/performances",
        json=_create_payload(),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Exercise prescription not found"


def test_list_performances_for_prescription_returns_only_the_services_result(
    authenticated_client, monkeypatch
):
    performances = [_performance_read_double()]
    monkeypatch.setattr(
        exercise_performances_service,
        "list_performances_for_prescription",
        lambda *a, **k: performances,
    )

    response = authenticated_client.get(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}/performances"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_performances_for_unowned_prescription_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExercisePrescriptionNotFoundError(
            PRESCRIPTION_ID
        )

    monkeypatch.setattr(
        exercise_performances_service, "list_performances_for_prescription", _raise
    )

    response = authenticated_client.get(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}/performances"
    )

    assert response.status_code == 404


def test_list_performances_for_session_returns_only_the_services_result(
    authenticated_client, monkeypatch
):
    performances = [_performance_read_double()]
    monkeypatch.setattr(
        exercise_performances_service,
        "list_performances_for_session",
        lambda *a, **k: performances,
    )

    response = authenticated_client.get(f"/workout-sessions/{SESSION_ID}/performances")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_performances_for_unowned_session_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise workout_sessions_service.WorkoutSessionAccessDeniedError(SESSION_ID)

    monkeypatch.setattr(
        exercise_performances_service, "list_performances_for_session", _raise
    )

    response = authenticated_client.get(f"/workout-sessions/{SESSION_ID}/performances")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Workout session not found"


def test_get_exercise_performance_owned_by_caller_returns_200(
    authenticated_client, monkeypatch
):
    performance = _performance_read_double()
    monkeypatch.setattr(
        exercise_performances_service,
        "get_owned_exercise_performance",
        lambda *a, **k: performance,
    )

    response = authenticated_client.get(f"/exercise-performances/{PERFORMANCE_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == PERFORMANCE_ID


def test_get_exercise_performance_owned_by_another_user_returns_404(
    authenticated_client, monkeypatch
):
    # Access-denied must be indistinguishable from not-found to the caller.
    def _raise(*args, **kwargs):
        raise exercise_performances_service.ExercisePerformanceAccessDeniedError(
            PERFORMANCE_ID
        )

    monkeypatch.setattr(
        exercise_performances_service, "get_owned_exercise_performance", _raise
    )

    response = authenticated_client.get(f"/exercise-performances/{PERFORMANCE_ID}")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Exercise performance not found"


def test_update_exercise_performance_owned_by_caller_returns_200(
    authenticated_client, monkeypatch
):
    updated = _performance_read_double()
    monkeypatch.setattr(
        exercise_performances_service,
        "update_exercise_performance",
        lambda *a, **k: updated,
    )

    response = authenticated_client.put(
        f"/exercise-performances/{PERFORMANCE_ID}", json={"actual_reps": 3}
    )

    assert response.status_code == 200


def test_update_exercise_performance_not_found_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_performances_service.ExercisePerformanceNotFoundError(
            PERFORMANCE_ID
        )

    monkeypatch.setattr(
        exercise_performances_service, "update_exercise_performance", _raise
    )

    response = authenticated_client.put(
        f"/exercise-performances/{PERFORMANCE_ID}", json={"actual_reps": 3}
    )

    assert response.status_code == 404


def test_update_exercise_performance_with_null_actual_reps_returns_422(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_performances_service.InvalidExercisePerformanceUpdateError(
            "actual_reps cannot be null"
        )

    monkeypatch.setattr(
        exercise_performances_service, "update_exercise_performance", _raise
    )

    response = authenticated_client.put(
        f"/exercise-performances/{PERFORMANCE_ID}", json={"actual_reps": None}
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "actual_reps cannot be null"


def test_delete_exercise_performance_owned_by_caller_returns_204(
    authenticated_client, monkeypatch
):
    delete_mock = MagicMock(return_value=None)
    monkeypatch.setattr(
        exercise_performances_service, "delete_exercise_performance", delete_mock
    )

    response = authenticated_client.delete(f"/exercise-performances/{PERFORMANCE_ID}")

    assert response.status_code == 204
    delete_mock.assert_called_once()


def test_delete_exercise_performance_access_denied_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_performances_service.ExercisePerformanceAccessDeniedError(
            PERFORMANCE_ID
        )

    monkeypatch.setattr(
        exercise_performances_service, "delete_exercise_performance", _raise
    )

    response = authenticated_client.delete(f"/exercise-performances/{PERFORMANCE_ID}")

    assert response.status_code == 404

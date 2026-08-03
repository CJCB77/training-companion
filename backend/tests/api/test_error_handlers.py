"""Tests for the global error envelope registered in app/core/error_handlers.py.

Covers all three handlers end to end, through the HTTP interface: the 500 fallback
for unhandled exceptions, the HTTPException handler (409/404/401), and the
RequestValidationError handler (422). The envelope shape itself (ErrorBody/
ErrorResponse) is declared in app/schemas/errors.py and not re-tested here beyond
what the response body demonstrates.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.models.enums import Equipment, MuscleGroup
from app.services import exercises as exercises_service
from app.services import programs as programs_service
from tests.factories import make_profile

PROGRAM_ID = 42
UNHANDLED_ERROR_MESSAGE = "boom: something exploded internally"


def _fake_session():
    # Every test here mocks the service layer, so the session is never used to
    # query anything — this just satisfies the route's Depends without needing a
    # real DATABASE_URL/engine (empty in CI).
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


@pytest.fixture
def authenticated_client_no_raise(current_user):
    """A client for the 500 path.

    TestClient(app) defaults to raise_server_exceptions=True, and
    ServerErrorMiddleware re-raises the original exception after our handler runs
    — so asserting on the *response* for a 500 requires this dedicated client.
    """
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session] = _fake_session
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_session, None)


def _create_exercise_payload(**overrides) -> dict:
    payload = {
        "name": "Bulgarian Split Squat",
        "muscle_group": MuscleGroup.QUADS.value,
        "equipment": Equipment.DUMBBELL.value,
    }
    payload.update(overrides)
    return payload


def test_unhandled_exception_returns_500_with_error_envelope(
    authenticated_client_no_raise, monkeypatch
):
    def _raise(*args, **kwargs):
        raise RuntimeError(UNHANDLED_ERROR_MESSAGE)

    monkeypatch.setattr(exercises_service, "list_exercises", _raise)

    response = authenticated_client_no_raise.get("/exercises")
    body = response.json()

    assert response.status_code == 500
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "Internal server error"
    assert body["error"]["details"] is None
    assert "error_id" in body["error"]


def test_unhandled_exception_response_does_not_leak_exception_details(
    authenticated_client_no_raise, monkeypatch
):
    def _raise(*args, **kwargs):
        raise RuntimeError(UNHANDLED_ERROR_MESSAGE)

    monkeypatch.setattr(exercises_service, "list_exercises", _raise)

    response = authenticated_client_no_raise.get("/exercises")

    assert UNHANDLED_ERROR_MESSAGE not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


def test_duplicate_exercise_name_returns_409_with_error_envelope(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercises_service.DuplicateExerciseNameError("Bulgarian Split Squat")

    monkeypatch.setattr(exercises_service, "create_custom_exercise", _raise)

    response = authenticated_client.post("/exercises", json=_create_exercise_payload())
    body = response.json()

    assert response.status_code == 409
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"] == "An exercise with that name already exists"
    assert body["error"]["details"] is None
    assert "error_id" in body["error"]


def test_program_not_found_returns_404_with_error_envelope(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramNotFoundError()

    monkeypatch.setattr(programs_service, "get_owned_program", _raise)

    response = authenticated_client.get(f"/programs/{PROGRAM_ID}")
    body = response.json()

    assert response.status_code == 404
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "Program not found"
    assert body["error"]["details"] is None
    assert "error_id" in body["error"]


def test_invalid_payload_returns_422_with_per_field_details(authenticated_client):
    response = authenticated_client.post(
        "/exercises", json=_create_exercise_payload(muscle_group="not-a-real-group")
    )
    body = response.json()

    assert response.status_code == 422
    assert body["error"]["code"] == "validation_error"
    details = body["error"]["details"]
    assert details
    assert any(detail["field"] == "body.muscle_group" for detail in details)
    assert all({"field", "message", "type"} == set(detail) for detail in details)


def test_invalid_payload_422_does_not_echo_submitted_value(authenticated_client):
    sentinel_value = "not-a-real-muscle-group-sentinel"

    response = authenticated_client.post(
        "/exercises", json=_create_exercise_payload(muscle_group=sentinel_value)
    )

    assert response.status_code == 422
    assert sentinel_value not in response.text


def test_unknown_route_returns_404_with_error_envelope(client):
    response = client.get("/no-such-route")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_wrong_method_on_known_route_returns_405_with_error_envelope(client):
    response = client.delete("/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in response.headers["allow"]


def test_invalid_token_returns_401_with_www_authenticate_header(client):
    response = client.get(
        "/exercises", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    body = response.json()

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert body["error"]["code"] == "unauthorized"
    assert "error_id" in body["error"]

"""Route-level tests for /programs.

The service layer is mocked here — business logic (ownership, partial updates) is
covered in tests/services/test_programs.py. These tests only verify HTTP wiring:
status codes, auth enforcement, response shape, and the not-found/access-denied
404 masking that happens at the route boundary.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.services import programs as programs_service
from tests.factories import make_profile, make_program

PROGRAM_ID = 42


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


def _program_read_double(user_id: int) -> object:
    program = make_program(user_id=user_id, name="Texas Method")
    program.id = PROGRAM_ID
    program.created_at = datetime.now(timezone.utc)
    program.updated_at = datetime.now(timezone.utc)
    return program


def test_create_program_without_auth_returns_401(client):
    payload = {"name": "My Strength Block"}

    response = client.post("/programs", json=payload)

    assert response.status_code == 401


def test_create_program_returns_201_and_created_program(
    authenticated_client, current_user, monkeypatch
):
    created = _program_read_double(current_user.id)
    monkeypatch.setattr(
        programs_service, "create_program_for_user", lambda *a, **k: created
    )
    payload = {"name": "My Strength Block"}

    response = authenticated_client.post("/programs", json=payload)

    assert response.status_code == 201
    assert response.json()["name"] == "Texas Method"
    assert response.json()["id"] == PROGRAM_ID


def test_list_programs_returns_only_the_services_result(
    authenticated_client, current_user, monkeypatch
):
    programs = [_program_read_double(current_user.id)]
    monkeypatch.setattr(programs_service, "list_programs", lambda *a, **k: programs)

    response = authenticated_client.get("/programs")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_program_owned_by_caller_returns_200(
    authenticated_client, current_user, monkeypatch
):
    program = _program_read_double(current_user.id)
    monkeypatch.setattr(programs_service, "get_owned_program", lambda *a, **k: program)

    response = authenticated_client.get(f"/programs/{PROGRAM_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == PROGRAM_ID


def test_get_program_that_does_not_exist_returns_404(authenticated_client, monkeypatch):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramNotFoundError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "get_owned_program", _raise)

    response = authenticated_client.get(f"/programs/{PROGRAM_ID}")

    assert response.status_code == 404


def test_get_program_owned_by_another_user_also_returns_404(
    authenticated_client, monkeypatch
):
    # Access-denied must be indistinguishable from not-found to the caller.
    def _raise(*args, **kwargs):
        raise programs_service.ProgramAccessDeniedError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "get_owned_program", _raise)

    response = authenticated_client.get(f"/programs/{PROGRAM_ID}")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Program not found"


def test_update_program_owned_by_caller_returns_200(
    authenticated_client, current_user, monkeypatch
):
    updated = _program_read_double(current_user.id)
    monkeypatch.setattr(programs_service, "update_program", lambda *a, **k: updated)

    response = authenticated_client.put(
        f"/programs/{PROGRAM_ID}", json={"name": "Renamed"}
    )

    assert response.status_code == 200


def test_update_program_not_found_returns_404(authenticated_client, monkeypatch):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramNotFoundError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "update_program", _raise)

    response = authenticated_client.put(
        f"/programs/{PROGRAM_ID}", json={"name": "Renamed"}
    )

    assert response.status_code == 404


def test_update_program_access_denied_returns_404(authenticated_client, monkeypatch):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramAccessDeniedError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "update_program", _raise)

    response = authenticated_client.put(
        f"/programs/{PROGRAM_ID}", json={"name": "Renamed"}
    )

    assert response.status_code == 404


def test_list_programs_passes_include_archived_query_param_through(
    authenticated_client, current_user, monkeypatch
):
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(programs_service, "list_programs", list_mock)

    response = authenticated_client.get("/programs?include_archived=true")

    assert response.status_code == 200
    _, called_kwargs = list_mock.call_args
    assert called_kwargs["include_archived"] is True


def test_archive_program_owned_by_caller_returns_200(
    authenticated_client, current_user, monkeypatch
):
    archived = _program_read_double(current_user.id)
    monkeypatch.setattr(programs_service, "archive_program", lambda *a, **k: archived)

    response = authenticated_client.post(f"/programs/{PROGRAM_ID}/archive")

    assert response.status_code == 200
    assert response.json()["id"] == PROGRAM_ID


def test_archive_program_not_found_returns_404(authenticated_client, monkeypatch):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramNotFoundError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "archive_program", _raise)

    response = authenticated_client.post(f"/programs/{PROGRAM_ID}/archive")

    assert response.status_code == 404


def test_archive_program_access_denied_returns_404(authenticated_client, monkeypatch):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramAccessDeniedError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "archive_program", _raise)

    response = authenticated_client.post(f"/programs/{PROGRAM_ID}/archive")

    assert response.status_code == 404


def test_unarchive_program_owned_by_caller_returns_200(
    authenticated_client, current_user, monkeypatch
):
    unarchived = _program_read_double(current_user.id)
    monkeypatch.setattr(
        programs_service, "unarchive_program", lambda *a, **k: unarchived
    )

    response = authenticated_client.post(f"/programs/{PROGRAM_ID}/unarchive")

    assert response.status_code == 200
    assert response.json()["id"] == PROGRAM_ID


def test_unarchive_program_not_found_returns_404(authenticated_client, monkeypatch):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramNotFoundError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "unarchive_program", _raise)

    response = authenticated_client.post(f"/programs/{PROGRAM_ID}/unarchive")

    assert response.status_code == 404


def test_unarchive_program_access_denied_returns_404(authenticated_client, monkeypatch):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramAccessDeniedError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "unarchive_program", _raise)

    response = authenticated_client.post(f"/programs/{PROGRAM_ID}/unarchive")

    assert response.status_code == 404


def test_delete_program_owned_by_caller_returns_204(authenticated_client, monkeypatch):
    delete_mock = MagicMock(return_value=None)
    monkeypatch.setattr(programs_service, "delete_program", delete_mock)

    response = authenticated_client.delete(f"/programs/{PROGRAM_ID}")

    assert response.status_code == 204
    delete_mock.assert_called_once()


def test_delete_program_not_found_returns_404(authenticated_client, monkeypatch):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramNotFoundError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "delete_program", _raise)

    response = authenticated_client.delete(f"/programs/{PROGRAM_ID}")

    assert response.status_code == 404


def test_delete_program_access_denied_returns_404(authenticated_client, monkeypatch):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramAccessDeniedError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "delete_program", _raise)

    response = authenticated_client.delete(f"/programs/{PROGRAM_ID}")

    assert response.status_code == 404


def test_create_program_with_unknown_progression_params_key_returns_422(
    authenticated_client,
):
    payload = {
        "name": "My Strength Block",
        "default_progression_params": {"unknown_key": 1},
    }

    response = authenticated_client.post("/programs", json=payload)

    assert response.status_code == 422


def test_create_program_with_out_of_range_percentage_returns_422(
    authenticated_client,
):
    payload = {
        "name": "My Strength Block",
        "default_progression_params": {"percentage": 1.5},
    }

    response = authenticated_client.post("/programs", json=payload)

    assert response.status_code == 422


def test_update_program_with_negative_increment_returns_422(authenticated_client):
    payload = {"default_progression_params": {"increment": -2.5}}

    response = authenticated_client.put(f"/programs/{PROGRAM_ID}", json=payload)

    assert response.status_code == 422


def test_update_program_with_invalid_deload_failure_threshold_returns_422(
    authenticated_client,
):
    payload = {
        "default_progression_params": {"deload": {"failure_threshold": 0}},
    }

    response = authenticated_client.put(f"/programs/{PROGRAM_ID}", json=payload)

    assert response.status_code == 422

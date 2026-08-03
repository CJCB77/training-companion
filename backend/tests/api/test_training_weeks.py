"""Route-level tests for training-week endpoints.

The service layer is mocked here — business logic (ownership, week-number
assignment/collision) is covered in tests/services/test_training_weeks.py. These
tests only verify HTTP wiring: status codes, auth enforcement, response shape, and
the not-found/access-denied 404 masking (both the week's own and its parent
program's) plus the 409 on a week-number collision.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.services import programs as programs_service
from app.services import training_weeks as training_weeks_service
from tests.factories import make_profile, make_training_week

PROGRAM_ID = 7
WEEK_ID = 42


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


def _week_read_double(**overrides) -> object:
    week = make_training_week(program_id=PROGRAM_ID, week_number=1, **overrides)
    week.id = WEEK_ID
    week.created_at = datetime.now(timezone.utc)
    week.updated_at = datetime.now(timezone.utc)
    return week


def test_create_training_week_without_auth_returns_401(client):
    response = client.post(f"/programs/{PROGRAM_ID}/training-weeks", json={})

    assert response.status_code == 401


def test_create_training_week_returns_201_and_created_week(
    authenticated_client, monkeypatch
):
    created = _week_read_double()
    monkeypatch.setattr(
        training_weeks_service,
        "create_training_week_for_program",
        lambda *a, **k: created,
    )

    response = authenticated_client.post(
        f"/programs/{PROGRAM_ID}/training-weeks", json={"name": "Week 1"}
    )

    assert response.status_code == 201
    assert response.json()["id"] == WEEK_ID


def test_create_training_week_for_unowned_program_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramAccessDeniedError(PROGRAM_ID)

    monkeypatch.setattr(
        training_weeks_service, "create_training_week_for_program", _raise
    )

    response = authenticated_client.post(
        f"/programs/{PROGRAM_ID}/training-weeks", json={}
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Program not found"


def test_create_training_week_with_taken_week_number_returns_409(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise training_weeks_service.DuplicateWeekNumberError(1)

    monkeypatch.setattr(
        training_weeks_service, "create_training_week_for_program", _raise
    )

    response = authenticated_client.post(
        f"/programs/{PROGRAM_ID}/training-weeks", json={"week_number": 1}
    )

    assert response.status_code == 409


def test_list_training_weeks_returns_only_the_services_result(
    authenticated_client, monkeypatch
):
    weeks = [_week_read_double()]
    monkeypatch.setattr(
        training_weeks_service, "list_training_weeks", lambda *a, **k: weeks
    )

    response = authenticated_client.get(f"/programs/{PROGRAM_ID}/training-weeks")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_training_weeks_for_unowned_program_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramNotFoundError(PROGRAM_ID)

    monkeypatch.setattr(training_weeks_service, "list_training_weeks", _raise)

    response = authenticated_client.get(f"/programs/{PROGRAM_ID}/training-weeks")

    assert response.status_code == 404


def test_get_training_week_owned_by_caller_returns_200(
    authenticated_client, monkeypatch
):
    week = _week_read_double()
    monkeypatch.setattr(
        training_weeks_service, "get_owned_training_week", lambda *a, **k: week
    )

    response = authenticated_client.get(f"/training-weeks/{WEEK_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == WEEK_ID


def test_get_training_week_that_does_not_exist_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise training_weeks_service.TrainingWeekNotFoundError(WEEK_ID)

    monkeypatch.setattr(training_weeks_service, "get_owned_training_week", _raise)

    response = authenticated_client.get(f"/training-weeks/{WEEK_ID}")

    assert response.status_code == 404


def test_get_training_week_owned_by_another_user_also_returns_404(
    authenticated_client, monkeypatch
):
    # Access-denied must be indistinguishable from not-found to the caller.
    def _raise(*args, **kwargs):
        raise training_weeks_service.TrainingWeekAccessDeniedError(WEEK_ID)

    monkeypatch.setattr(training_weeks_service, "get_owned_training_week", _raise)

    response = authenticated_client.get(f"/training-weeks/{WEEK_ID}")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Training week not found"


def test_update_training_week_owned_by_caller_returns_200(
    authenticated_client, monkeypatch
):
    updated = _week_read_double()
    monkeypatch.setattr(
        training_weeks_service, "update_training_week", lambda *a, **k: updated
    )

    response = authenticated_client.put(
        f"/training-weeks/{WEEK_ID}", json={"name": "Deload"}
    )

    assert response.status_code == 200


def test_update_training_week_not_found_returns_404(authenticated_client, monkeypatch):
    def _raise(*args, **kwargs):
        raise training_weeks_service.TrainingWeekNotFoundError(WEEK_ID)

    monkeypatch.setattr(training_weeks_service, "update_training_week", _raise)

    response = authenticated_client.put(
        f"/training-weeks/{WEEK_ID}", json={"name": "Deload"}
    )

    assert response.status_code == 404


def test_update_training_week_with_taken_week_number_returns_409(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise training_weeks_service.DuplicateWeekNumberError(2)

    monkeypatch.setattr(training_weeks_service, "update_training_week", _raise)

    response = authenticated_client.put(
        f"/training-weeks/{WEEK_ID}", json={"week_number": 2}
    )

    assert response.status_code == 409


def test_delete_training_week_owned_by_caller_returns_204(
    authenticated_client, monkeypatch
):
    delete_mock = MagicMock(return_value=None)
    monkeypatch.setattr(training_weeks_service, "delete_training_week", delete_mock)

    response = authenticated_client.delete(f"/training-weeks/{WEEK_ID}")

    assert response.status_code == 204
    delete_mock.assert_called_once()


def test_delete_training_week_access_denied_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise training_weeks_service.TrainingWeekAccessDeniedError(WEEK_ID)

    monkeypatch.setattr(training_weeks_service, "delete_training_week", _raise)

    response = authenticated_client.delete(f"/training-weeks/{WEEK_ID}")

    assert response.status_code == 404


def test_update_training_week_with_null_week_number_returns_422(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise training_weeks_service.InvalidTrainingWeekUpdateError(
            "week_number cannot be null"
        )

    monkeypatch.setattr(training_weeks_service, "update_training_week", _raise)

    response = authenticated_client.put(
        f"/training-weeks/{WEEK_ID}", json={"week_number": None}
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "week_number cannot be null"

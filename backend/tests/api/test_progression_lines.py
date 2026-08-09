"""Route-level tests for progression-line endpoints.

The service layer is mocked here — ownership enforcement is covered in
tests/services/test_progression_lines.py. These tests only verify HTTP wiring:
status codes, auth enforcement, response shape, and the not-found/access-denied
404 masking.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.services import programs as programs_service
from app.services import progression_lines as progression_lines_service
from tests.factories import make_profile, make_progression_line

PROGRAM_ID = 3
EXERCISE_ID = 20
LINE_ID = 99


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


def _line_read_double(**overrides) -> object:
    data = {"program_id": PROGRAM_ID, "exercise_id": EXERCISE_ID}
    data.update(overrides)
    line = make_progression_line(**data)
    line.id = LINE_ID
    line.created_at = datetime.now(timezone.utc)
    line.updated_at = datetime.now(timezone.utc)
    return line


def test_list_progression_lines_without_auth_returns_401(client):
    response = client.get(
        f"/programs/{PROGRAM_ID}/exercises/{EXERCISE_ID}/progression-lines"
    )

    assert response.status_code == 401


def test_list_progression_lines_returns_200_and_default_first(
    authenticated_client, monkeypatch
):
    default_line = _line_read_double(is_default=True)
    explicit_line = _line_read_double(id=LINE_ID + 1, is_default=False, label="Light")
    monkeypatch.setattr(
        progression_lines_service,
        "list_progression_lines",
        lambda *a, **k: [default_line, explicit_line],
    )

    response = authenticated_client.get(
        f"/programs/{PROGRAM_ID}/exercises/{EXERCISE_ID}/progression-lines"
    )

    assert response.status_code == 200
    body = response.json()
    assert [line["id"] for line in body] == [default_line.id, explicit_line.id]
    assert body[0]["is_default"] is True


def test_list_progression_lines_for_unowned_program_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramAccessDeniedError(PROGRAM_ID)

    monkeypatch.setattr(progression_lines_service, "list_progression_lines", _raise)

    response = authenticated_client.get(
        f"/programs/{PROGRAM_ID}/exercises/{EXERCISE_ID}/progression-lines"
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Program not found"


def test_rename_progression_line_without_auth_returns_401(client):
    response = client.patch(f"/progression-lines/{LINE_ID}", json={"label": "Light"})

    assert response.status_code == 401


def test_rename_progression_line_owned_by_caller_returns_200_with_new_label(
    authenticated_client, monkeypatch
):
    renamed = _line_read_double(label="Light")
    monkeypatch.setattr(
        progression_lines_service,
        "rename_progression_line",
        lambda *a, **k: renamed,
    )

    response = authenticated_client.patch(
        f"/progression-lines/{LINE_ID}", json={"label": "Light"}
    )

    assert response.status_code == 200
    assert response.json()["label"] == "Light"


def test_rename_progression_line_owned_by_another_user_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise progression_lines_service.ProgressionLineAccessDeniedError(LINE_ID)

    monkeypatch.setattr(progression_lines_service, "rename_progression_line", _raise)

    response = authenticated_client.patch(
        f"/progression-lines/{LINE_ID}", json={"label": "Light"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Progression line not found"


def test_rename_progression_line_not_found_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise progression_lines_service.ProgressionLineNotFoundError(LINE_ID)

    monkeypatch.setattr(progression_lines_service, "rename_progression_line", _raise)

    response = authenticated_client.patch(
        f"/progression-lines/{LINE_ID}", json={"label": "Light"}
    )

    assert response.status_code == 404

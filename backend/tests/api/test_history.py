"""Route-level tests for /history endpoints.

The service layer is mocked here — ownership/PR/e1RM-trend logic is covered in
tests/services/test_history.py. These tests only verify HTTP wiring: status
codes, auth enforcement, response shape, and not-found/access-denied masking.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.models.enums import PersonalRecordKind, WeightUnit
from app.schemas.history import (
    CompletedSessionRead,
    OneRmTrendPointRead,
    PersonalRecordRead,
)
from app.services import history as history_service
from tests.factories import make_profile

PROGRAM_ID = 3
EXERCISE_ID = 20
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


def _completed_session() -> CompletedSessionRead:
    return CompletedSessionRead(
        id=SESSION_ID,
        program_id=PROGRAM_ID,
        week_id=1,
        day_name="Day A",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        notes=None,
    )


def _personal_record(**overrides) -> PersonalRecordRead:
    data = {
        "exercise_id": EXERCISE_ID,
        "exercise_name": "Squat",
        "kind": PersonalRecordKind.HEAVIEST_WEIGHT,
        "value": 140.0,
        "recorded_unit": WeightUnit.KG,
        "display_value": 140.0,
        "display_unit": WeightUnit.KG,
        "converted": False,
        "reps": 5,
        "performed_at": datetime.now(timezone.utc),
        "workout_session_id": SESSION_ID,
        "program_id": PROGRAM_ID,
        "progression_line_id": 7,
    }
    data.update(overrides)
    return PersonalRecordRead(**data)


def _trend_point(**overrides) -> OneRmTrendPointRead:
    data = {
        "exercise_id": EXERCISE_ID,
        "exercise_name": "Squat",
        "value": 160.0,
        "recorded_unit": WeightUnit.KG,
        "display_value": 160.0,
        "display_unit": WeightUnit.KG,
        "converted": False,
        "reps": 5,
        "performed_at": datetime.now(timezone.utc),
        "workout_session_id": SESSION_ID,
        "program_id": PROGRAM_ID,
        "progression_line_id": 7,
    }
    data.update(overrides)
    return OneRmTrendPointRead(**data)


# --------------------------------------------------------------------------
# GET /history/sessions
# --------------------------------------------------------------------------


def test_list_completed_sessions_without_auth_returns_401(client):
    response = client.get("/history/sessions")

    assert response.status_code == 401


def test_list_completed_sessions_returns_200_and_the_service_result(
    authenticated_client, monkeypatch
):
    session_read = _completed_session()
    monkeypatch.setattr(
        history_service, "list_completed_sessions", lambda *a, **k: [session_read]
    )

    response = authenticated_client.get("/history/sessions")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [session_read.id]


def test_list_completed_sessions_for_unowned_program_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise history_service.ProgramAccessDeniedError(PROGRAM_ID)

    monkeypatch.setattr(history_service, "list_completed_sessions", _raise)

    response = authenticated_client.get(
        "/history/sessions", params={"program_id": PROGRAM_ID}
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Program not found"


# --------------------------------------------------------------------------
# GET /history/personal-records
# --------------------------------------------------------------------------


def test_get_personal_records_without_auth_returns_401(client):
    response = client.get(
        "/history/personal-records", params={"exercise_id": EXERCISE_ID}
    )

    assert response.status_code == 401


def test_get_personal_records_returns_200_and_the_service_result(
    authenticated_client, monkeypatch
):
    record = _personal_record()
    monkeypatch.setattr(
        history_service, "get_personal_records", lambda *a, **k: [record]
    )

    response = authenticated_client.get(
        "/history/personal-records", params={"exercise_id": EXERCISE_ID}
    )

    assert response.status_code == 200
    assert response.json()[0]["kind"] == PersonalRecordKind.HEAVIEST_WEIGHT.value


def test_get_personal_records_for_unknown_exercise_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise history_service.ExerciseNotFoundError(EXERCISE_ID)

    monkeypatch.setattr(history_service, "get_personal_records", _raise)

    response = authenticated_client.get(
        "/history/personal-records", params={"exercise_id": EXERCISE_ID}
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Exercise not found"


# --------------------------------------------------------------------------
# GET /history/sessions/{session_id}/personal-records
# --------------------------------------------------------------------------


def test_get_session_personal_records_without_auth_returns_401(client):
    response = client.get(f"/history/sessions/{SESSION_ID}/personal-records")

    assert response.status_code == 401


def test_get_session_personal_records_returns_200_and_the_service_result(
    authenticated_client, monkeypatch
):
    record = _personal_record()
    monkeypatch.setattr(
        history_service, "get_session_personal_records", lambda *a, **k: [record]
    )

    response = authenticated_client.get(
        f"/history/sessions/{SESSION_ID}/personal-records"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_session_personal_records_for_unowned_session_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise history_service.WorkoutSessionAccessDeniedError(SESSION_ID)

    monkeypatch.setattr(history_service, "get_session_personal_records", _raise)

    response = authenticated_client.get(
        f"/history/sessions/{SESSION_ID}/personal-records"
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Workout session not found"


# --------------------------------------------------------------------------
# GET /history/exercises/{exercise_id}/one-rm-trend
# --------------------------------------------------------------------------


def test_get_one_rm_trend_without_auth_returns_401(client):
    response = client.get(f"/history/exercises/{EXERCISE_ID}/one-rm-trend")

    assert response.status_code == 401


def test_get_one_rm_trend_returns_200_and_the_service_result(
    authenticated_client, monkeypatch
):
    point = _trend_point()
    monkeypatch.setattr(history_service, "get_one_rm_trend", lambda *a, **k: [point])

    response = authenticated_client.get(
        f"/history/exercises/{EXERCISE_ID}/one-rm-trend"
    )

    assert response.status_code == 200
    assert response.json()[0]["workout_session_id"] == point.workout_session_id


def test_get_one_rm_trend_for_unknown_exercise_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise history_service.ExerciseNotFoundError(EXERCISE_ID)

    monkeypatch.setattr(history_service, "get_one_rm_trend", _raise)

    response = authenticated_client.get(
        f"/history/exercises/{EXERCISE_ID}/one-rm-trend"
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Exercise not found"


def test_get_one_rm_trend_with_limit_over_the_maximum_returns_422(
    authenticated_client,
):
    response = authenticated_client.get(
        f"/history/exercises/{EXERCISE_ID}/one-rm-trend",
        params={"limit": history_service.MAX_LIST_LIMIT + 1},
    )

    assert response.status_code == 422

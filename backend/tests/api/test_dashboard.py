"""Route-level tests for GET /dashboard.

The service layer is mocked here — the resume/continue and PR/trend fold
logic is covered in tests/services/test_dashboard.py. These tests only verify
HTTP wiring: auth enforcement, status code, and response shape.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.models.enums import WeightUnit
from app.schemas.dashboard import ConsistencyRead, DashboardRead
from app.services import dashboard as dashboard_service
from tests.factories import make_profile


def _fake_session():
    yield MagicMock()


@pytest.fixture
def current_user():
    user = make_profile(default_weight_unit=WeightUnit.KG)
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


def _dashboard_read() -> DashboardRead:
    return DashboardRead(
        active_program=None,
        program_progress=None,
        next_workout=None,
        program_complete=False,
        consistency=ConsistencyRead(
            sessions_completed_last_7_days=0,
            sessions_completed_last_28_days=0,
            days_since_last_session=None,
        ),
        recent_personal_records=[],
        exercise_trends=[],
    )


def test_get_dashboard_without_auth_returns_401(client):
    response = client.get("/dashboard")

    assert response.status_code == 401


def test_get_dashboard_returns_200_and_the_service_result(
    authenticated_client, monkeypatch
):
    dashboard_read = _dashboard_read()
    monkeypatch.setattr(
        dashboard_service, "get_dashboard", lambda *a, **k: dashboard_read
    )

    response = authenticated_client.get("/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["active_program"] is None
    assert body["program_complete"] is False
    assert body["consistency"]["sessions_completed_last_28_days"] == 0


def test_get_dashboard_scopes_the_query_by_the_authenticated_user(
    authenticated_client, current_user, monkeypatch
):
    get_dashboard_mock = MagicMock(return_value=_dashboard_read())
    monkeypatch.setattr(dashboard_service, "get_dashboard", get_dashboard_mock)

    authenticated_client.get("/dashboard")

    _args, kwargs = get_dashboard_mock.call_args
    assert kwargs["user_id"] == current_user.id
    assert kwargs["display_unit"] == current_user.default_weight_unit

"""Route-level tests for the progression-recommendation endpoint.

The engine itself is covered directly (no DB, no mocking) in
tests/services/test_progression.py. These tests only verify HTTP wiring: auth
enforcement, the not-found/access-denied 404 masking, and response shape.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.models.enums import ProgressionType
from app.schemas.progression import (
    DeloadSettings,
    ProgressionSettings,
    RecommendationRead,
)
from app.services import exercise_prescriptions as exercise_prescriptions_service
from app.services import progression as progression_service
from tests.factories import make_profile

PRESCRIPTION_ID = 42


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


def _recommendation_read_double(**overrides) -> RecommendationRead:
    data = {
        "recommended_weight": 102.5,
        "current_weight": 100.0,
        "action": "increase",
        "progression_type": ProgressionType.FIXED_INCREMENT,
        "consecutive_failures": 0,
        "reason": "Last attempt succeeded — increase by the fixed increment.",
        "settings_used": ProgressionSettings(
            progression_type=ProgressionType.FIXED_INCREMENT,
            increment=2.5,
            percentage=None,
            rounding_increment=2.5,
            deload=DeloadSettings(enabled=True, failure_threshold=3, percentage=0.10),
        ),
    }
    data.update(overrides)
    return RecommendationRead(**data)


def test_get_recommendation_without_auth_returns_401(client):
    response = client.get(
        f"/progression/exercise-prescriptions/{PRESCRIPTION_ID}/recommendation"
    )

    assert response.status_code == 401


def test_get_recommendation_returns_200_and_response_shape(
    authenticated_client, monkeypatch
):
    recommendation = _recommendation_read_double()
    monkeypatch.setattr(
        progression_service,
        "get_recommendation_for_prescription",
        lambda *a, **k: recommendation,
    )

    response = authenticated_client.get(
        f"/progression/exercise-prescriptions/{PRESCRIPTION_ID}/recommendation"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "increase"
    assert body["recommended_weight"] == 102.5
    assert body["current_weight"] == 100.0
    assert body["progression_type"] == ProgressionType.FIXED_INCREMENT.value
    assert body["settings_used"]["deload"]["failure_threshold"] == 3


def test_get_recommendation_for_unowned_prescription_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError(
            PRESCRIPTION_ID
        )

    monkeypatch.setattr(
        progression_service, "get_recommendation_for_prescription", _raise
    )

    response = authenticated_client.get(
        f"/progression/exercise-prescriptions/{PRESCRIPTION_ID}/recommendation"
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Exercise prescription not found"


def test_get_recommendation_for_nonexistent_prescription_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExercisePrescriptionNotFoundError(
            PRESCRIPTION_ID
        )

    monkeypatch.setattr(
        progression_service, "get_recommendation_for_prescription", _raise
    )

    response = authenticated_client.get(
        f"/progression/exercise-prescriptions/{PRESCRIPTION_ID}/recommendation"
    )

    assert response.status_code == 404

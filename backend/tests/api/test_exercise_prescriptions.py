"""Route-level tests for exercise-prescription endpoints.

The service layer is mocked here — business logic (ownership, order_index
assignment, exercise-visibility validation) is covered in
tests/services/test_exercise_prescriptions.py. These tests only verify HTTP
wiring: status codes, auth enforcement, response shape, and the not-found/
access-denied 404 masking (the prescription's own, its parent workout session's,
and the referenced exercise's).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.services import exercise_prescriptions as exercise_prescriptions_service
from app.services import workout_sessions as workout_sessions_service
from tests.factories import make_exercise_prescription, make_profile

SESSION_ID = 7
EXERCISE_ID = 20
PRESCRIPTION_ID = 42
PROGRESSION_LINE_ID = 99


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


def _prescription_read_double(**overrides) -> object:
    data = {
        "workout_session_id": SESSION_ID,
        "exercise_id": EXERCISE_ID,
        "progression_line_id": PROGRESSION_LINE_ID,
    }
    data.update(overrides)
    prescription = make_exercise_prescription(**data)
    prescription.id = PRESCRIPTION_ID
    prescription.created_at = datetime.now(timezone.utc)
    prescription.updated_at = datetime.now(timezone.utc)
    return prescription


def _create_payload(**overrides) -> dict:
    payload = {"exercise_id": EXERCISE_ID, "target_sets": 5, "target_reps": 5}
    payload.update(overrides)
    return payload


def test_create_exercise_prescription_without_auth_returns_401(client):
    response = client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions",
        json=_create_payload(),
    )

    assert response.status_code == 401


def test_create_exercise_prescription_returns_201_and_created_prescription(
    authenticated_client, monkeypatch
):
    created = _prescription_read_double()
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "create_exercise_prescription_for_session",
        lambda *a, **k: created,
    )

    response = authenticated_client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions",
        json=_create_payload(),
    )

    assert response.status_code == 201
    assert response.json()["id"] == PRESCRIPTION_ID


def test_create_exercise_prescription_for_unowned_session_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise workout_sessions_service.WorkoutSessionAccessDeniedError(SESSION_ID)

    monkeypatch.setattr(
        exercise_prescriptions_service,
        "create_exercise_prescription_for_session",
        _raise,
    )

    response = authenticated_client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions",
        json=_create_payload(),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Workout session not found"


def test_create_exercise_prescription_with_invisible_exercise_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExerciseNotVisibleError(EXERCISE_ID)

    monkeypatch.setattr(
        exercise_prescriptions_service,
        "create_exercise_prescription_for_session",
        _raise,
    )

    response = authenticated_client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions",
        json=_create_payload(),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Exercise not found"


def test_list_exercise_prescriptions_returns_only_the_services_result(
    authenticated_client, monkeypatch
):
    prescriptions = [_prescription_read_double()]
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "list_exercise_prescriptions",
        lambda *a, **k: prescriptions,
    )

    response = authenticated_client.get(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_exercise_prescription_owned_by_caller_returns_200(
    authenticated_client, monkeypatch
):
    prescription = _prescription_read_double()
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "get_owned_exercise_prescription",
        lambda *a, **k: prescription,
    )

    response = authenticated_client.get(f"/exercise-prescriptions/{PRESCRIPTION_ID}")

    assert response.status_code == 200
    assert response.json()["id"] == PRESCRIPTION_ID


def test_get_exercise_prescription_owned_by_another_user_returns_404(
    authenticated_client, monkeypatch
):
    # Access-denied must be indistinguishable from not-found to the caller.
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError(
            PRESCRIPTION_ID
        )

    monkeypatch.setattr(
        exercise_prescriptions_service, "get_owned_exercise_prescription", _raise
    )

    response = authenticated_client.get(f"/exercise-prescriptions/{PRESCRIPTION_ID}")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Exercise prescription not found"


def test_update_exercise_prescription_owned_by_caller_returns_200(
    authenticated_client, monkeypatch
):
    updated = _prescription_read_double()
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "update_exercise_prescription",
        lambda *a, **k: updated,
    )

    response = authenticated_client.put(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}", json={"target_sets": 3}
    )

    assert response.status_code == 200


def test_update_exercise_prescription_with_invisible_exercise_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExerciseNotVisibleError(EXERCISE_ID)

    monkeypatch.setattr(
        exercise_prescriptions_service, "update_exercise_prescription", _raise
    )

    response = authenticated_client.put(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}",
        json={"exercise_id": EXERCISE_ID},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Exercise not found"


def test_update_exercise_prescription_not_found_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExercisePrescriptionNotFoundError(
            PRESCRIPTION_ID
        )

    monkeypatch.setattr(
        exercise_prescriptions_service, "update_exercise_prescription", _raise
    )

    response = authenticated_client.put(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}", json={"target_sets": 3}
    )

    assert response.status_code == 404


def test_delete_exercise_prescription_owned_by_caller_returns_204(
    authenticated_client, monkeypatch
):
    delete_mock = MagicMock(return_value=None)
    monkeypatch.setattr(
        exercise_prescriptions_service, "delete_exercise_prescription", delete_mock
    )

    response = authenticated_client.delete(f"/exercise-prescriptions/{PRESCRIPTION_ID}")

    assert response.status_code == 204
    delete_mock.assert_called_once()


def test_delete_exercise_prescription_access_denied_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError(
            PRESCRIPTION_ID
        )

    monkeypatch.setattr(
        exercise_prescriptions_service, "delete_exercise_prescription", _raise
    )

    response = authenticated_client.delete(f"/exercise-prescriptions/{PRESCRIPTION_ID}")

    assert response.status_code == 404


def test_update_exercise_prescription_with_null_exercise_id_returns_422(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.InvalidExercisePrescriptionUpdateError(
            "exercise_id cannot be null"
        )

    monkeypatch.setattr(
        exercise_prescriptions_service, "update_exercise_prescription", _raise
    )

    response = authenticated_client.put(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}", json={"exercise_id": None}
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "exercise_id cannot be null"


def test_create_exercise_prescription_with_unknown_progression_params_key_returns_422(
    authenticated_client,
):
    payload = _create_payload(progression_params={"unknown_key": 1})

    response = authenticated_client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions", json=payload
    )

    assert response.status_code == 422


def test_create_exercise_prescription_with_out_of_range_percentage_returns_422(
    authenticated_client,
):
    payload = _create_payload(progression_params={"percentage": 0})

    response = authenticated_client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions", json=payload
    )

    assert response.status_code == 422


def test_update_exercise_prescription_with_negative_increment_returns_422(
    authenticated_client,
):
    payload = {"progression_params": {"increment": -2.5}}

    response = authenticated_client.put(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}", json=payload
    )

    assert response.status_code == 422


def test_update_exercise_prescription_with_invalid_deload_percentage_returns_422(
    authenticated_client,
):
    payload = {"progression_params": {"deload": {"percentage": 1.0}}}

    response = authenticated_client.put(
        f"/exercise-prescriptions/{PRESCRIPTION_ID}", json=payload
    )

    assert response.status_code == 422


def test_create_exercise_prescription_with_no_progression_line_fields_passes_them_through(
    authenticated_client, monkeypatch
):
    created = _prescription_read_double()
    create_mock = MagicMock(return_value=created)
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "create_exercise_prescription_for_session",
        create_mock,
    )

    response = authenticated_client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions",
        json=_create_payload(),
    )

    assert response.status_code == 201
    payload = create_mock.call_args.kwargs["payload"]
    assert payload.progression_line_id is None
    assert payload.start_new_progression_line is None


def test_create_exercise_prescription_with_existing_progression_line_id_passes_it_through(
    authenticated_client, monkeypatch
):
    created = _prescription_read_double()
    create_mock = MagicMock(return_value=created)
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "create_exercise_prescription_for_session",
        create_mock,
    )

    response = authenticated_client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions",
        json=_create_payload(progression_line_id=PROGRESSION_LINE_ID),
    )

    assert response.status_code == 201
    payload = create_mock.call_args.kwargs["payload"]
    assert payload.progression_line_id == PROGRESSION_LINE_ID
    assert payload.start_new_progression_line is None


def test_create_exercise_prescription_with_start_new_progression_line_passes_it_through(
    authenticated_client, monkeypatch
):
    created = _prescription_read_double()
    create_mock = MagicMock(return_value=created)
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "create_exercise_prescription_for_session",
        create_mock,
    )

    response = authenticated_client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions",
        json=_create_payload(start_new_progression_line={"label": "Light"}),
    )

    assert response.status_code == 201
    payload = create_mock.call_args.kwargs["payload"]
    assert payload.progression_line_id is None
    assert payload.start_new_progression_line.label == "Light"


def test_create_exercise_prescription_with_both_progression_line_fields_returns_422(
    authenticated_client,
):
    payload = _create_payload(
        progression_line_id=PROGRESSION_LINE_ID,
        start_new_progression_line={"label": "Light"},
    )

    response = authenticated_client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions", json=payload
    )

    assert response.status_code == 422


def test_create_exercise_prescription_with_invalid_progression_line_reference_returns_422(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.InvalidProgressionLineReferenceError(
            PROGRESSION_LINE_ID
        )

    monkeypatch.setattr(
        exercise_prescriptions_service,
        "create_exercise_prescription_for_session",
        _raise,
    )

    response = authenticated_client.post(
        f"/workout-sessions/{SESSION_ID}/exercise-prescriptions",
        json=_create_payload(progression_line_id=PROGRESSION_LINE_ID),
    )

    assert response.status_code == 422

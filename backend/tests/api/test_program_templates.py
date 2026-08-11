"""Route-level tests for /program-templates.

The service layer is mocked here — the actual generation algorithm and its
progression-line grouping are covered in tests/services/test_program_templates.py.
These tests only verify HTTP wiring: status codes, auth enforcement, response
shape, and the 404 on an unknown template id.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.main import app
from app.models.enums import ProgressionType, WeightUnit
from app.services import program_templates as program_templates_service
from tests.factories import make_profile, make_program, make_program_template

TEMPLATE_ID = 7


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


def _template_double(**overrides) -> object:
    data = {
        "slug": "stronglifts-5x5",
        "name": "StrongLifts 5x5",
        "description": "Beginner linear progression.",
        "weight_unit": WeightUnit.KG,
        "default_progression_type": ProgressionType.FIXED_INCREMENT,
        "default_progression_params": {"increment": 2.5},
        "structure": {"weeks": []},
    }
    data.update(overrides)
    template = make_program_template(**data)
    template.id = TEMPLATE_ID
    template.created_at = datetime.now(timezone.utc)
    template.updated_at = datetime.now(timezone.utc)
    return template


def _program_read_double(user_id: int) -> object:
    program = make_program(user_id=user_id, name="StrongLifts 5x5")
    program.id = 42
    program.created_at = datetime.now(timezone.utc)
    program.updated_at = datetime.now(timezone.utc)
    return program


def test_list_program_templates_without_auth_returns_401(client):
    response = client.get("/program-templates")

    assert response.status_code == 401


def test_list_program_templates_returns_200_and_shape(
    authenticated_client, monkeypatch
):
    monkeypatch.setattr(
        program_templates_service,
        "list_templates",
        lambda *a, **k: [_template_double()],
    )

    response = authenticated_client.get("/program-templates")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["slug"] == "stronglifts-5x5"
    assert "structure" not in body[0]


def test_get_program_template_returns_200_and_includes_structure(
    authenticated_client, monkeypatch
):
    monkeypatch.setattr(
        program_templates_service, "get_template", lambda *a, **k: _template_double()
    )

    response = authenticated_client.get(f"/program-templates/{TEMPLATE_ID}")

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "stronglifts-5x5"
    assert body["structure"] == {"weeks": []}


def test_get_program_template_for_unknown_id_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise program_templates_service.ProgramTemplateNotFoundError(TEMPLATE_ID)

    monkeypatch.setattr(program_templates_service, "get_template", _raise)

    response = authenticated_client.get(f"/program-templates/{TEMPLATE_ID}")

    assert response.status_code == 404


def test_generate_program_from_template_returns_201_and_program(
    authenticated_client, current_user, monkeypatch
):
    generated = _program_read_double(current_user.id)
    monkeypatch.setattr(
        program_templates_service,
        "generate_program_from_template",
        lambda *a, **k: generated,
    )

    response = authenticated_client.post(
        f"/program-templates/{TEMPLATE_ID}/generate", json={"name": "My Copy"}
    )

    assert response.status_code == 201
    assert response.json()["id"] == generated.id
    assert response.json()["name"] == "StrongLifts 5x5"


def test_generate_program_from_template_with_no_body_returns_201(
    authenticated_client, current_user, monkeypatch
):
    """Zero-typing generate — a client that sends no body at all must still work,
    matching TRAIN-23's duplicate-program precedent. Regression guard for the route
    param needing a real default, not just an optional field.
    """
    generated = _program_read_double(current_user.id)
    monkeypatch.setattr(
        program_templates_service,
        "generate_program_from_template",
        lambda *a, **k: generated,
    )

    response = authenticated_client.post(f"/program-templates/{TEMPLATE_ID}/generate")

    assert response.status_code == 201


def test_generate_program_from_template_for_unknown_id_returns_404(
    authenticated_client, monkeypatch
):
    def _raise(*args, **kwargs):
        raise program_templates_service.ProgramTemplateNotFoundError(TEMPLATE_ID)

    monkeypatch.setattr(
        program_templates_service, "generate_program_from_template", _raise
    )

    response = authenticated_client.post(f"/program-templates/{TEMPLATE_ID}/generate")

    assert response.status_code == 404


def test_generate_program_from_template_without_auth_returns_401(client):
    response = client.post(f"/program-templates/{TEMPLATE_ID}/generate")

    assert response.status_code == 401

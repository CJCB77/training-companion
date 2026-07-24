"""Unit tests for app.services.programs.

The repository layer is external I/O, so it's mocked here — these tests exercise
the ownership enforcement and partial-update orchestration that actually lives in
the service, not the database.
"""

from unittest.mock import MagicMock

import pytest

from app.schemas.programs import ProgramCreate, ProgramUpdate
from app.services import programs as programs_service
from tests.factories import make_program

OWNER_ID = 1
OTHER_USER_ID = 2
PROGRAM_ID = 42


def _owned_program(*, user_id: int = OWNER_ID, **overrides) -> object:
    program = make_program(user_id=user_id, **overrides)
    program.id = PROGRAM_ID
    return program


def test_get_owned_program_returns_program_when_owned(monkeypatch):
    # Arrange
    program = _owned_program()
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )

    # Act
    result = programs_service.get_owned_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
    )

    # Assert
    assert result is program


def test_get_owned_program_missing_program_raises_not_found(monkeypatch):
    # Arrange
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: None
    )

    # Act / Assert
    with pytest.raises(programs_service.ProgramNotFoundError):
        programs_service.get_owned_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )


def test_get_owned_program_belonging_to_other_user_raises_access_denied(monkeypatch):
    # Arrange
    program = _owned_program(user_id=OTHER_USER_ID)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )

    # Act / Assert
    with pytest.raises(programs_service.ProgramAccessDeniedError):
        programs_service.get_owned_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )


def test_update_program_applies_only_explicitly_set_fields(monkeypatch):
    # Arrange
    program = _owned_program(name="Original", description="Original description")
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    update_mock = MagicMock(side_effect=lambda session, prog, **fields: prog)
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    payload = ProgramUpdate(name="Renamed")

    # Act
    programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    # Assert
    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"name": "Renamed"}


def test_update_program_with_no_fields_set_does_not_call_repo_update(monkeypatch):
    # Arrange
    program = _owned_program()
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    update_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    payload = ProgramUpdate()

    # Act
    result = programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    # Assert
    update_mock.assert_not_called()
    assert result is program


def test_update_program_can_explicitly_clear_a_nullable_field(monkeypatch):
    # Arrange
    program = _owned_program(description="Has a description")
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    update_mock = MagicMock(side_effect=lambda session, prog, **fields: prog)
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    # Explicitly passing description=None (as opposed to omitting the key) mirrors
    # a client sending {"description": null} to clear the field.
    payload = ProgramUpdate(description=None)

    # Act
    programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    # Assert
    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"description": None}


def test_update_program_for_missing_program_raises_not_found(monkeypatch):
    # Arrange
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: None
    )

    # Act / Assert
    with pytest.raises(programs_service.ProgramNotFoundError):
        programs_service.update_program(
            MagicMock(),
            user_id=OWNER_ID,
            program_id=PROGRAM_ID,
            payload=ProgramUpdate(name="Anything"),
        )


def test_update_program_for_other_users_program_raises_access_denied(monkeypatch):
    # Arrange
    program = _owned_program(user_id=OTHER_USER_ID)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )

    # Act / Assert
    with pytest.raises(programs_service.ProgramAccessDeniedError):
        programs_service.update_program(
            MagicMock(),
            user_id=OWNER_ID,
            program_id=PROGRAM_ID,
            payload=ProgramUpdate(name="Anything"),
        )


def test_delete_program_soft_deletes_owned_program(monkeypatch):
    # Arrange
    program = _owned_program()
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    soft_delete_mock = MagicMock()
    monkeypatch.setattr(
        programs_service.programs_repo, "soft_delete_program", soft_delete_mock
    )

    # Act
    programs_service.delete_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
    )

    # Assert
    soft_delete_mock.assert_called_once()
    assert soft_delete_mock.call_args[0][1] is program


def test_delete_program_for_missing_program_raises_not_found(monkeypatch):
    # Arrange
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: None
    )
    soft_delete_mock = MagicMock()
    monkeypatch.setattr(
        programs_service.programs_repo, "soft_delete_program", soft_delete_mock
    )

    # Act / Assert
    with pytest.raises(programs_service.ProgramNotFoundError):
        programs_service.delete_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )
    soft_delete_mock.assert_not_called()


def test_delete_program_for_other_users_program_raises_access_denied(monkeypatch):
    # Arrange
    program = _owned_program(user_id=OTHER_USER_ID)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    soft_delete_mock = MagicMock()
    monkeypatch.setattr(
        programs_service.programs_repo, "soft_delete_program", soft_delete_mock
    )

    # Act / Assert
    with pytest.raises(programs_service.ProgramAccessDeniedError):
        programs_service.delete_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )
    soft_delete_mock.assert_not_called()


def test_create_program_for_user_with_is_active_true_deactivates_others_first(
    monkeypatch,
):
    # Arrange
    created = _owned_program()
    create_mock = MagicMock(return_value=created)
    deactivate_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "create_program", create_mock)
    monkeypatch.setattr(
        programs_service.programs_repo,
        "deactivate_other_active_programs",
        deactivate_mock,
    )
    payload = ProgramCreate(name="New Block", is_active=True)
    session = MagicMock()

    # Act
    programs_service.create_program_for_user(session, user_id=OWNER_ID, payload=payload)

    # Assert
    deactivate_mock.assert_called_once_with(session, OWNER_ID)
    create_mock.assert_called_once()


def test_create_program_for_user_with_is_active_false_does_not_deactivate_others(
    monkeypatch,
):
    # Arrange
    created = _owned_program()
    create_mock = MagicMock(return_value=created)
    deactivate_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "create_program", create_mock)
    monkeypatch.setattr(
        programs_service.programs_repo,
        "deactivate_other_active_programs",
        deactivate_mock,
    )
    payload = ProgramCreate(name="New Block", is_active=False)
    session = MagicMock()

    # Act
    programs_service.create_program_for_user(session, user_id=OWNER_ID, payload=payload)

    # Assert
    deactivate_mock.assert_not_called()
    create_mock.assert_called_once()


def test_update_program_setting_is_active_true_deactivates_others_first(monkeypatch):
    # Arrange
    program = _owned_program(is_active=False)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    update_mock = MagicMock(side_effect=lambda session, prog, **fields: prog)
    deactivate_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    monkeypatch.setattr(
        programs_service.programs_repo,
        "deactivate_other_active_programs",
        deactivate_mock,
    )
    session = MagicMock()
    payload = ProgramUpdate(is_active=True)

    # Act
    programs_service.update_program(
        session, user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    # Assert
    deactivate_mock.assert_called_once_with(
        session, OWNER_ID, exclude_program_id=PROGRAM_ID
    )
    update_mock.assert_called_once()


def test_update_program_setting_is_active_false_does_not_deactivate_others(
    monkeypatch,
):
    # Arrange
    program = _owned_program(is_active=True)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    update_mock = MagicMock(side_effect=lambda session, prog, **fields: prog)
    deactivate_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    monkeypatch.setattr(
        programs_service.programs_repo,
        "deactivate_other_active_programs",
        deactivate_mock,
    )
    payload = ProgramUpdate(is_active=False)

    # Act
    programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    # Assert
    deactivate_mock.assert_not_called()


def test_update_program_without_touching_is_active_does_not_deactivate_others(
    monkeypatch,
):
    # Arrange
    program = _owned_program(is_active=True, name="Original")
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    update_mock = MagicMock(side_effect=lambda session, prog, **fields: prog)
    deactivate_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    monkeypatch.setattr(
        programs_service.programs_repo,
        "deactivate_other_active_programs",
        deactivate_mock,
    )
    payload = ProgramUpdate(name="Renamed")

    # Act
    programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    # Assert
    deactivate_mock.assert_not_called()


def test_list_programs_scopes_to_the_given_user(monkeypatch):
    # Arrange
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(
        programs_service.programs_repo, "list_programs_for_user", list_mock
    )
    session = MagicMock()

    # Act
    programs_service.list_programs(session, user_id=OWNER_ID)

    # Assert
    list_mock.assert_called_once_with(session, user_id=OWNER_ID)

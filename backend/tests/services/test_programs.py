"""Unit tests for app.services.programs.

The repository layer is external I/O, so it's mocked here — these tests exercise
the ownership enforcement and partial-update orchestration that actually lives in
the service, not the database.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.schemas.programs import ProgramCreate, ProgramUpdate
from app.schemas.progression import ProgressionParams
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
    program = _owned_program()
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )

    result = programs_service.get_owned_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
    )

    assert result is program


def test_get_owned_program_missing_program_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: None
    )

    with pytest.raises(programs_service.ProgramNotFoundError):
        programs_service.get_owned_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )


def test_get_owned_program_belonging_to_other_user_raises_access_denied(monkeypatch):
    program = _owned_program(user_id=OTHER_USER_ID)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )

    with pytest.raises(programs_service.ProgramAccessDeniedError):
        programs_service.get_owned_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )


def test_update_program_applies_only_explicitly_set_fields(monkeypatch):
    program = _owned_program(name="Original", description="Original description")
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    update_mock = MagicMock(side_effect=lambda session, prog, **fields: prog)
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    payload = ProgramUpdate(name="Renamed")

    programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"name": "Renamed"}


def test_update_program_with_no_fields_set_does_not_call_repo_update(monkeypatch):
    program = _owned_program()
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    update_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    payload = ProgramUpdate()

    result = programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    update_mock.assert_not_called()
    assert result is program


def test_update_program_can_explicitly_clear_a_nullable_field(monkeypatch):
    program = _owned_program(description="Has a description")
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    update_mock = MagicMock(side_effect=lambda session, prog, **fields: prog)
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    # Explicitly passing description=None (as opposed to omitting the key) mirrors
    # a client sending {"description": null} to clear the field.
    payload = ProgramUpdate(description=None)

    programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"description": None}


def test_update_program_for_missing_program_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: None
    )

    with pytest.raises(programs_service.ProgramNotFoundError):
        programs_service.update_program(
            MagicMock(),
            user_id=OWNER_ID,
            program_id=PROGRAM_ID,
            payload=ProgramUpdate(name="Anything"),
        )


def test_update_program_for_other_users_program_raises_access_denied(monkeypatch):
    program = _owned_program(user_id=OTHER_USER_ID)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )

    with pytest.raises(programs_service.ProgramAccessDeniedError):
        programs_service.update_program(
            MagicMock(),
            user_id=OWNER_ID,
            program_id=PROGRAM_ID,
            payload=ProgramUpdate(name="Anything"),
        )


def test_delete_program_hard_deletes_owned_program(monkeypatch):
    program = _owned_program()
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "delete_program", delete_mock)

    programs_service.delete_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
    )

    delete_mock.assert_called_once()
    assert delete_mock.call_args[0][1] is program


def test_delete_program_for_missing_program_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: None
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "delete_program", delete_mock)

    with pytest.raises(programs_service.ProgramNotFoundError):
        programs_service.delete_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )
    delete_mock.assert_not_called()


def test_delete_program_for_other_users_program_raises_access_denied(monkeypatch):
    program = _owned_program(user_id=OTHER_USER_ID)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "delete_program", delete_mock)

    with pytest.raises(programs_service.ProgramAccessDeniedError):
        programs_service.delete_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )
    delete_mock.assert_not_called()


def test_archive_program_archives_owned_program(monkeypatch):
    program = _owned_program()
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    archive_mock = MagicMock(return_value=program)
    monkeypatch.setattr(programs_service.programs_repo, "archive_program", archive_mock)

    result = programs_service.archive_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
    )

    archive_mock.assert_called_once()
    assert archive_mock.call_args[0][1] is program
    assert result is program


def test_archive_program_for_missing_program_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: None
    )
    archive_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "archive_program", archive_mock)

    with pytest.raises(programs_service.ProgramNotFoundError):
        programs_service.archive_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )
    archive_mock.assert_not_called()


def test_archive_program_for_other_users_program_raises_access_denied(monkeypatch):
    program = _owned_program(user_id=OTHER_USER_ID)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    archive_mock = MagicMock()
    monkeypatch.setattr(programs_service.programs_repo, "archive_program", archive_mock)

    with pytest.raises(programs_service.ProgramAccessDeniedError):
        programs_service.archive_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )
    archive_mock.assert_not_called()


def test_unarchive_program_unarchives_owned_program(monkeypatch):
    program = _owned_program()
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    unarchive_mock = MagicMock(return_value=program)
    monkeypatch.setattr(
        programs_service.programs_repo, "unarchive_program", unarchive_mock
    )

    result = programs_service.unarchive_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
    )

    unarchive_mock.assert_called_once()
    assert unarchive_mock.call_args[0][1] is program
    assert result is program


def test_unarchive_program_for_missing_program_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: None
    )
    unarchive_mock = MagicMock()
    monkeypatch.setattr(
        programs_service.programs_repo, "unarchive_program", unarchive_mock
    )

    with pytest.raises(programs_service.ProgramNotFoundError):
        programs_service.unarchive_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )
    unarchive_mock.assert_not_called()


def test_unarchive_program_for_other_users_program_raises_access_denied(monkeypatch):
    program = _owned_program(user_id=OTHER_USER_ID)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    unarchive_mock = MagicMock()
    monkeypatch.setattr(
        programs_service.programs_repo, "unarchive_program", unarchive_mock
    )

    with pytest.raises(programs_service.ProgramAccessDeniedError):
        programs_service.unarchive_program(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )
    unarchive_mock.assert_not_called()


def test_create_program_for_user_with_is_active_true_deactivates_others_first(
    monkeypatch,
):
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

    programs_service.create_program_for_user(session, user_id=OWNER_ID, payload=payload)

    deactivate_mock.assert_called_once_with(session, OWNER_ID)
    create_mock.assert_called_once()


def test_create_program_for_user_with_is_active_false_does_not_deactivate_others(
    monkeypatch,
):
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

    programs_service.create_program_for_user(session, user_id=OWNER_ID, payload=payload)

    deactivate_mock.assert_not_called()
    create_mock.assert_called_once()


def test_create_program_dumps_progression_params_to_a_plain_dict(monkeypatch):
    # The real break risk flagged in TRAIN-20's design plan: SQLModel won't
    # serialize a ProgressionParams instance into the JSONB column, so the
    # repository must receive a plain dict, not the Pydantic model.
    create_mock = MagicMock(return_value=_owned_program())
    monkeypatch.setattr(programs_service.programs_repo, "create_program", create_mock)
    payload = ProgramCreate(
        name="New Block",
        default_progression_params=ProgressionParams(increment=2.5),
    )

    programs_service.create_program_for_user(
        MagicMock(), user_id=OWNER_ID, payload=payload
    )

    _, called_kwargs = create_mock.call_args
    dumped = called_kwargs["default_progression_params"]
    assert dumped == {"increment": 2.5}
    assert type(dumped) is dict


def test_update_program_dumps_progression_params_to_a_plain_dict(monkeypatch):
    program = _owned_program()
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    update_mock = MagicMock(side_effect=lambda session, prog, **fields: prog)
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    payload = ProgramUpdate(
        default_progression_params=ProgressionParams(percentage=0.025)
    )

    programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    _, called_kwargs = update_mock.call_args
    dumped = called_kwargs["default_progression_params"]
    assert dumped == {"percentage": 0.025}
    assert type(dumped) is dict


def test_update_program_setting_is_active_true_deactivates_others_first(monkeypatch):
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

    programs_service.update_program(
        session, user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    deactivate_mock.assert_called_once_with(
        session, OWNER_ID, exclude_program_id=PROGRAM_ID
    )
    update_mock.assert_called_once()


def test_update_program_setting_is_active_false_does_not_deactivate_others(
    monkeypatch,
):
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

    programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    deactivate_mock.assert_not_called()


def test_update_program_activating_an_archived_program_unarchives_it_first(
    monkeypatch,
):
    program = _owned_program(is_active=False)
    program.archived_at = datetime.now(timezone.utc)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    unarchive_mock = MagicMock(side_effect=lambda session, prog: prog)
    monkeypatch.setattr(
        programs_service.programs_repo, "unarchive_program", unarchive_mock
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

    programs_service.update_program(
        session, user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    unarchive_mock.assert_called_once_with(session, program)
    deactivate_mock.assert_called_once_with(
        session, OWNER_ID, exclude_program_id=PROGRAM_ID
    )


def test_update_program_activating_a_non_archived_program_does_not_unarchive(
    monkeypatch,
):
    program = _owned_program(is_active=False)
    monkeypatch.setattr(
        programs_service.programs_repo, "get_program", lambda *a, **k: program
    )
    unarchive_mock = MagicMock(side_effect=lambda session, prog: prog)
    monkeypatch.setattr(
        programs_service.programs_repo, "unarchive_program", unarchive_mock
    )
    update_mock = MagicMock(side_effect=lambda session, prog, **fields: prog)
    monkeypatch.setattr(programs_service.programs_repo, "update_program", update_mock)
    monkeypatch.setattr(
        programs_service.programs_repo,
        "deactivate_other_active_programs",
        MagicMock(),
    )
    payload = ProgramUpdate(is_active=True)

    programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    unarchive_mock.assert_not_called()


def test_update_program_without_touching_is_active_does_not_deactivate_others(
    monkeypatch,
):
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

    programs_service.update_program(
        MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID, payload=payload
    )

    deactivate_mock.assert_not_called()


def test_list_programs_scopes_to_the_given_user(monkeypatch):
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(
        programs_service.programs_repo, "list_programs_for_user", list_mock
    )
    session = MagicMock()

    programs_service.list_programs(session, user_id=OWNER_ID)

    list_mock.assert_called_once_with(session, user_id=OWNER_ID, include_archived=False)


def test_list_programs_passes_include_archived_through_to_the_repo(monkeypatch):
    list_mock = MagicMock(return_value=[])
    monkeypatch.setattr(
        programs_service.programs_repo, "list_programs_for_user", list_mock
    )
    session = MagicMock()

    programs_service.list_programs(session, user_id=OWNER_ID, include_archived=True)

    list_mock.assert_called_once_with(session, user_id=OWNER_ID, include_archived=True)

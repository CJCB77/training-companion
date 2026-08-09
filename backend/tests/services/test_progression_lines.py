"""Unit tests for app.services.progression_lines.

The repository layer and the parent Program ownership check are external I/O, so
they're mocked here — these tests exercise ownership enforcement and the
label-only nature of renaming.
"""

from unittest.mock import MagicMock

import pytest

from app.schemas.progression_lines import ProgressionLineUpdate
from app.services import programs as programs_service
from app.services import progression_lines as progression_lines_service
from tests.factories import make_progression_line

OWNER_ID = 1
OTHER_USER_ID = 2
PROGRAM_ID = 3
EXERCISE_ID = 20
LINE_ID = 99


def _line(**overrides) -> object:
    data = {"program_id": PROGRAM_ID, "exercise_id": EXERCISE_ID}
    data.update(overrides)
    line = make_progression_line(**data)
    line.id = LINE_ID
    return line


def test_get_owned_progression_line_returns_line_when_owned(monkeypatch):
    line = _line()
    monkeypatch.setattr(
        progression_lines_service.progression_lines_repo,
        "get_progression_line_with_owner",
        lambda *a, **k: (line, OWNER_ID),
    )

    result = progression_lines_service.get_owned_progression_line(
        MagicMock(), user_id=OWNER_ID, line_id=LINE_ID
    )

    assert result is line


def test_get_owned_progression_line_missing_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        progression_lines_service.progression_lines_repo,
        "get_progression_line_with_owner",
        lambda *a, **k: None,
    )

    with pytest.raises(progression_lines_service.ProgressionLineNotFoundError):
        progression_lines_service.get_owned_progression_line(
            MagicMock(), user_id=OWNER_ID, line_id=LINE_ID
        )


def test_get_owned_progression_line_belonging_to_other_user_raises_access_denied(
    monkeypatch,
):
    line = _line()
    monkeypatch.setattr(
        progression_lines_service.progression_lines_repo,
        "get_progression_line_with_owner",
        lambda *a, **k: (line, OTHER_USER_ID),
    )

    with pytest.raises(progression_lines_service.ProgressionLineAccessDeniedError):
        progression_lines_service.get_owned_progression_line(
            MagicMock(), user_id=OWNER_ID, line_id=LINE_ID
        )


def test_list_progression_lines_checks_program_ownership_first(monkeypatch):
    get_program_mock = MagicMock()
    monkeypatch.setattr(programs_service, "get_owned_program", get_program_mock)
    monkeypatch.setattr(
        progression_lines_service.progression_lines_repo,
        "list_progression_lines",
        lambda *a, **k: [],
    )
    session = MagicMock()

    progression_lines_service.list_progression_lines(
        session, user_id=OWNER_ID, program_id=PROGRAM_ID, exercise_id=EXERCISE_ID
    )

    get_program_mock.assert_called_once_with(
        session, user_id=OWNER_ID, program_id=PROGRAM_ID
    )


def test_list_progression_lines_for_unowned_program_raises_access_denied(
    monkeypatch,
):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramAccessDeniedError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "get_owned_program", _raise)

    with pytest.raises(programs_service.ProgramAccessDeniedError):
        progression_lines_service.list_progression_lines(
            MagicMock(),
            user_id=OWNER_ID,
            program_id=PROGRAM_ID,
            exercise_id=EXERCISE_ID,
        )


def test_rename_progression_line_updates_only_the_label(monkeypatch):
    line = _line(label=None)
    monkeypatch.setattr(
        progression_lines_service.progression_lines_repo,
        "get_progression_line_with_owner",
        lambda *a, **k: (line, OWNER_ID),
    )
    update_mock = MagicMock(side_effect=lambda session, ln, label: ln)
    monkeypatch.setattr(
        progression_lines_service.progression_lines_repo,
        "update_progression_line_label",
        update_mock,
    )

    progression_lines_service.rename_progression_line(
        MagicMock(),
        user_id=OWNER_ID,
        line_id=LINE_ID,
        payload=ProgressionLineUpdate(label="Light"),
    )

    _, called_line, called_label = update_mock.call_args[0]
    assert called_line is line
    assert called_label == "Light"


def test_rename_progression_line_with_empty_payload_is_a_no_op(monkeypatch):
    # exclude_unset=True: an empty PATCH body must not clear the label — only an
    # explicit {"label": null} does that (that key is set, just to None).
    line = _line(label="Original")
    monkeypatch.setattr(
        progression_lines_service.progression_lines_repo,
        "get_progression_line_with_owner",
        lambda *a, **k: (line, OWNER_ID),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        progression_lines_service.progression_lines_repo,
        "update_progression_line_label",
        update_mock,
    )

    result = progression_lines_service.rename_progression_line(
        MagicMock(), user_id=OWNER_ID, line_id=LINE_ID, payload=ProgressionLineUpdate()
    )

    update_mock.assert_not_called()
    assert result is line


def test_rename_progression_line_for_other_users_line_raises_access_denied(
    monkeypatch,
):
    line = _line()
    monkeypatch.setattr(
        progression_lines_service.progression_lines_repo,
        "get_progression_line_with_owner",
        lambda *a, **k: (line, OTHER_USER_ID),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        progression_lines_service.progression_lines_repo,
        "update_progression_line_label",
        update_mock,
    )

    with pytest.raises(progression_lines_service.ProgressionLineAccessDeniedError):
        progression_lines_service.rename_progression_line(
            MagicMock(),
            user_id=OWNER_ID,
            line_id=LINE_ID,
            payload=ProgressionLineUpdate(label="Light"),
        )
    update_mock.assert_not_called()

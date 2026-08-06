"""Unit tests for app.services.training_weeks.

The repository layer (and the parent Program ownership check) is external I/O, so
it's mocked here — these tests exercise ownership enforcement and week-number
auto-assignment/collision handling that actually lives in the service.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.schemas.training_weeks import TrainingWeekCreate, TrainingWeekUpdate
from app.services import programs as programs_service
from app.services import training_weeks as training_weeks_service
from tests.factories import make_training_week

OWNER_ID = 1
OTHER_USER_ID = 2
PROGRAM_ID = 10
WEEK_ID = 100


def _week(*, week_number: int = 1, **overrides) -> object:
    week = make_training_week(
        program_id=PROGRAM_ID, week_number=week_number, **overrides
    )
    week.id = WEEK_ID
    return week


def test_get_owned_training_week_returns_week_when_owned(monkeypatch):
    week = _week()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OWNER_ID),
    )

    result = training_weeks_service.get_owned_training_week(
        MagicMock(), user_id=OWNER_ID, week_id=WEEK_ID
    )

    assert result is week


def test_get_owned_training_week_missing_week_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: None,
    )

    with pytest.raises(training_weeks_service.TrainingWeekNotFoundError):
        training_weeks_service.get_owned_training_week(
            MagicMock(), user_id=OWNER_ID, week_id=WEEK_ID
        )


def test_get_owned_training_week_belonging_to_other_user_raises_access_denied(
    monkeypatch,
):
    week = _week()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OTHER_USER_ID),
    )

    with pytest.raises(training_weeks_service.TrainingWeekAccessDeniedError):
        training_weeks_service.get_owned_training_week(
            MagicMock(), user_id=OWNER_ID, week_id=WEEK_ID
        )


def test_list_training_weeks_checks_parent_program_ownership_first(monkeypatch):
    get_program_mock = MagicMock()
    monkeypatch.setattr(programs_service, "get_owned_program", get_program_mock)
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "list_training_weeks_for_program",
        lambda *a, **k: [],
    )
    session = MagicMock()

    training_weeks_service.list_training_weeks(
        session, user_id=OWNER_ID, program_id=PROGRAM_ID
    )

    get_program_mock.assert_called_once_with(
        session, user_id=OWNER_ID, program_id=PROGRAM_ID
    )


def test_list_training_weeks_for_unowned_program_raises_program_not_found(
    monkeypatch,
):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramNotFoundError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "get_owned_program", _raise)

    with pytest.raises(programs_service.ProgramNotFoundError):
        training_weeks_service.list_training_weeks(
            MagicMock(), user_id=OWNER_ID, program_id=PROGRAM_ID
        )


def test_create_training_week_with_no_week_number_assigns_one_for_first_week(
    monkeypatch,
):
    monkeypatch.setattr(programs_service, "get_owned_program", MagicMock())
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_max_week_number",
        lambda *a, **k: None,
    )
    create_mock = MagicMock(return_value=_week(week_number=1))
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "create_training_week", create_mock
    )

    training_weeks_service.create_training_week_for_program(
        MagicMock(),
        user_id=OWNER_ID,
        program_id=PROGRAM_ID,
        payload=TrainingWeekCreate(),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["week_number"] == 1


def test_create_training_week_with_no_week_number_assigns_max_plus_one(monkeypatch):
    monkeypatch.setattr(programs_service, "get_owned_program", MagicMock())
    existing_max_week_number = 3
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_max_week_number",
        lambda *a, **k: existing_max_week_number,
    )
    create_mock = MagicMock(
        return_value=_week(week_number=existing_max_week_number + 1)
    )
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "create_training_week", create_mock
    )

    training_weeks_service.create_training_week_for_program(
        MagicMock(),
        user_id=OWNER_ID,
        program_id=PROGRAM_ID,
        payload=TrainingWeekCreate(),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["week_number"] == existing_max_week_number + 1


def test_create_training_week_with_explicit_week_number_uses_it(monkeypatch):
    monkeypatch.setattr(programs_service, "get_owned_program", MagicMock())
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "find_by_week_number",
        lambda *a, **k: None,
    )
    create_mock = MagicMock(return_value=_week(week_number=5))
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "create_training_week", create_mock
    )

    training_weeks_service.create_training_week_for_program(
        MagicMock(),
        user_id=OWNER_ID,
        program_id=PROGRAM_ID,
        payload=TrainingWeekCreate(week_number=5),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["week_number"] == 5


def test_create_training_week_for_unowned_program_raises_program_not_found(
    monkeypatch,
):
    def _raise(*args, **kwargs):
        raise programs_service.ProgramNotFoundError(PROGRAM_ID)

    monkeypatch.setattr(programs_service, "get_owned_program", _raise)
    create_mock = MagicMock()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "create_training_week", create_mock
    )

    with pytest.raises(programs_service.ProgramNotFoundError):
        training_weeks_service.create_training_week_for_program(
            MagicMock(),
            user_id=OWNER_ID,
            program_id=PROGRAM_ID,
            payload=TrainingWeekCreate(),
        )
    create_mock.assert_not_called()


def test_create_training_week_with_taken_week_number_raises_duplicate(monkeypatch):
    monkeypatch.setattr(programs_service, "get_owned_program", MagicMock())
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "find_by_week_number",
        lambda *a, **k: _week(week_number=2),
    )
    create_mock = MagicMock()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "create_training_week", create_mock
    )

    with pytest.raises(training_weeks_service.DuplicateWeekNumberError):
        training_weeks_service.create_training_week_for_program(
            MagicMock(),
            user_id=OWNER_ID,
            program_id=PROGRAM_ID,
            payload=TrainingWeekCreate(week_number=2),
        )
    create_mock.assert_not_called()


def test_create_training_week_raises_duplicate_on_race_lost_at_commit(monkeypatch):
    # Simulates two concurrent requests both passing the upfront check before
    # either commits: the repo's insert then hits uq_training_week_program_number
    # and raises IntegrityError, which the service must translate to the same
    # public error the pre-check path raises, and must roll back the session.
    monkeypatch.setattr(programs_service, "get_owned_program", MagicMock())
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "find_by_week_number",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "create_training_week",
        MagicMock(side_effect=IntegrityError("INSERT", {}, Exception("dup"))),
    )
    session = MagicMock()

    with pytest.raises(training_weeks_service.DuplicateWeekNumberError):
        training_weeks_service.create_training_week_for_program(
            session,
            user_id=OWNER_ID,
            program_id=PROGRAM_ID,
            payload=TrainingWeekCreate(week_number=2),
        )
    session.rollback.assert_called_once()


def test_update_training_week_applies_only_explicitly_set_fields(monkeypatch):
    week = _week(name="Original")
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OWNER_ID),
    )
    update_mock = MagicMock(side_effect=lambda session, wk, **fields: wk)
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "update_training_week", update_mock
    )
    payload = TrainingWeekUpdate(name="Deload Week")

    training_weeks_service.update_training_week(
        MagicMock(), user_id=OWNER_ID, week_id=WEEK_ID, payload=payload
    )

    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"name": "Deload Week"}


def test_update_training_week_with_no_fields_set_does_not_call_repo_update(
    monkeypatch,
):
    week = _week()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OWNER_ID),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "update_training_week", update_mock
    )

    result = training_weeks_service.update_training_week(
        MagicMock(), user_id=OWNER_ID, week_id=WEEK_ID, payload=TrainingWeekUpdate()
    )

    update_mock.assert_not_called()
    assert result is week


def test_update_training_week_for_missing_week_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: None,
    )

    with pytest.raises(training_weeks_service.TrainingWeekNotFoundError):
        training_weeks_service.update_training_week(
            MagicMock(),
            user_id=OWNER_ID,
            week_id=WEEK_ID,
            payload=TrainingWeekUpdate(name="Anything"),
        )


def test_update_training_week_for_other_users_week_raises_access_denied(monkeypatch):
    week = _week()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OTHER_USER_ID),
    )

    with pytest.raises(training_weeks_service.TrainingWeekAccessDeniedError):
        training_weeks_service.update_training_week(
            MagicMock(),
            user_id=OWNER_ID,
            week_id=WEEK_ID,
            payload=TrainingWeekUpdate(name="Anything"),
        )


def test_update_training_week_to_an_unchanged_week_number_does_not_check_collision(
    monkeypatch,
):
    week = _week(week_number=3)
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OWNER_ID),
    )
    find_mock = MagicMock()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "find_by_week_number", find_mock
    )
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "update_training_week",
        MagicMock(side_effect=lambda session, wk, **fields: wk),
    )

    training_weeks_service.update_training_week(
        MagicMock(),
        user_id=OWNER_ID,
        week_id=WEEK_ID,
        payload=TrainingWeekUpdate(week_number=3),
    )

    find_mock.assert_not_called()


def test_update_training_week_to_a_week_number_taken_by_another_week_raises_duplicate(
    monkeypatch,
):
    week = _week(week_number=1)
    occupant = _week(week_number=2)
    occupant.id = WEEK_ID + 1
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OWNER_ID),
    )
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "find_by_week_number",
        lambda *a, **k: occupant,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "update_training_week", update_mock
    )

    with pytest.raises(training_weeks_service.DuplicateWeekNumberError):
        training_weeks_service.update_training_week(
            MagicMock(),
            user_id=OWNER_ID,
            week_id=WEEK_ID,
            payload=TrainingWeekUpdate(week_number=2),
        )
    update_mock.assert_not_called()


def test_delete_training_week_deletes_owned_week(monkeypatch):
    week = _week()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OWNER_ID),
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "delete_training_week", delete_mock
    )

    training_weeks_service.delete_training_week(
        MagicMock(), user_id=OWNER_ID, week_id=WEEK_ID
    )

    delete_mock.assert_called_once()
    assert delete_mock.call_args[0][1] is week


def test_delete_training_week_for_other_users_week_raises_access_denied(monkeypatch):
    week = _week()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OTHER_USER_ID),
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "delete_training_week", delete_mock
    )

    with pytest.raises(training_weeks_service.TrainingWeekAccessDeniedError):
        training_weeks_service.delete_training_week(
            MagicMock(), user_id=OWNER_ID, week_id=WEEK_ID
        )
    delete_mock.assert_not_called()


def test_update_training_week_with_null_week_number_raises_invalid_update(
    monkeypatch,
):
    week = _week(week_number=3)
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OWNER_ID),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "update_training_week", update_mock
    )
    payload = TrainingWeekUpdate(week_number=None)

    with pytest.raises(training_weeks_service.InvalidTrainingWeekUpdateError):
        training_weeks_service.update_training_week(
            MagicMock(), user_id=OWNER_ID, week_id=WEEK_ID, payload=payload
        )
    update_mock.assert_not_called()


def test_update_training_week_with_null_name_proceeds_normally(monkeypatch):
    # name is genuinely nullable — explicitly clearing it must not be rejected
    # by the same guard that blocks a null week_number.
    week = _week(name="Deload Week")
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OWNER_ID),
    )
    update_mock = MagicMock(side_effect=lambda session, wk, **fields: wk)
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "update_training_week", update_mock
    )
    payload = TrainingWeekUpdate(name=None)

    training_weeks_service.update_training_week(
        MagicMock(), user_id=OWNER_ID, week_id=WEEK_ID, payload=payload
    )

    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"name": None}


def test_create_training_week_with_auto_assigned_number_retries_once_on_lost_race(
    monkeypatch,
):
    monkeypatch.setattr(programs_service, "get_owned_program", MagicMock())
    max_week_numbers = iter([2, 3])
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_max_week_number",
        lambda *a, **k: next(max_week_numbers),
    )
    create_mock = MagicMock(
        side_effect=[
            IntegrityError("INSERT", {}, Exception("dup")),
            _week(week_number=4),
        ]
    )
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "create_training_week", create_mock
    )
    session = MagicMock()

    result = training_weeks_service.create_training_week_for_program(
        session,
        user_id=OWNER_ID,
        program_id=PROGRAM_ID,
        payload=TrainingWeekCreate(),
    )

    assert create_mock.call_count == 2
    first_attempt_kwargs = create_mock.call_args_list[0].kwargs
    second_attempt_kwargs = create_mock.call_args_list[1].kwargs
    assert first_attempt_kwargs["week_number"] == 3
    assert second_attempt_kwargs["week_number"] == 4
    assert result.week_number == 4
    session.rollback.assert_called_once()


def test_create_training_week_with_explicit_number_does_not_retry_on_lost_race(
    monkeypatch,
):
    monkeypatch.setattr(programs_service, "get_owned_program", MagicMock())
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "find_by_week_number",
        lambda *a, **k: None,
    )
    create_mock = MagicMock(side_effect=IntegrityError("INSERT", {}, Exception("dup")))
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo, "create_training_week", create_mock
    )
    session = MagicMock()

    with pytest.raises(training_weeks_service.DuplicateWeekNumberError):
        training_weeks_service.create_training_week_for_program(
            session,
            user_id=OWNER_ID,
            program_id=PROGRAM_ID,
            payload=TrainingWeekCreate(week_number=5),
        )

    create_mock.assert_called_once()


def test_update_training_week_unrelated_integrity_error_propagates(monkeypatch):
    # An IntegrityError raised by an update that never touched week_number is a
    # genuine, unexpected DB error — it must not be mis-mapped onto
    # DuplicateWeekNumberError, which would misreport a 409 about a week number
    # the request never mentioned.
    week = _week(week_number=1, name="Original")
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "get_training_week_with_owner",
        lambda *a, **k: (week, OWNER_ID),
    )
    unrelated_error = IntegrityError("UPDATE", {}, Exception("unrelated"))
    monkeypatch.setattr(
        training_weeks_service.training_weeks_repo,
        "update_training_week",
        MagicMock(side_effect=unrelated_error),
    )
    session = MagicMock()

    with pytest.raises(IntegrityError):
        training_weeks_service.update_training_week(
            session,
            user_id=OWNER_ID,
            week_id=WEEK_ID,
            payload=TrainingWeekUpdate(name="Renamed"),
        )
    session.rollback.assert_called_once()

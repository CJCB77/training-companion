"""Unit tests for app.services.workout_sessions.

The repository layer (and the parent TrainingWeek ownership check) is external
I/O, so it's mocked here — these tests exercise ownership enforcement and
order_index auto-assignment that actually lives in the service.
"""

from unittest.mock import MagicMock

import pytest

from app.schemas.workout_sessions import WorkoutSessionCreate, WorkoutSessionUpdate
from app.services import training_weeks as training_weeks_service
from app.services import workout_sessions as workout_sessions_service
from tests.factories import make_workout_session

OWNER_ID = 1
OTHER_USER_ID = 2
WEEK_ID = 10
SESSION_ID = 100


def _session(**overrides) -> object:
    workout_session = make_workout_session(week_id=WEEK_ID, **overrides)
    workout_session.id = SESSION_ID
    return workout_session


def test_get_owned_workout_session_returns_session_when_owned(monkeypatch):
    workout_session = _session()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_workout_session_with_owner",
        lambda *a, **k: (workout_session, OWNER_ID),
    )

    result = workout_sessions_service.get_owned_workout_session(
        MagicMock(), user_id=OWNER_ID, workout_session_id=SESSION_ID
    )

    assert result is workout_session


def test_get_owned_workout_session_missing_session_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_workout_session_with_owner",
        lambda *a, **k: None,
    )

    with pytest.raises(workout_sessions_service.WorkoutSessionNotFoundError):
        workout_sessions_service.get_owned_workout_session(
            MagicMock(), user_id=OWNER_ID, workout_session_id=SESSION_ID
        )


def test_get_owned_workout_session_belonging_to_other_user_raises_access_denied(
    monkeypatch,
):
    workout_session = _session()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_workout_session_with_owner",
        lambda *a, **k: (workout_session, OTHER_USER_ID),
    )

    with pytest.raises(workout_sessions_service.WorkoutSessionAccessDeniedError):
        workout_sessions_service.get_owned_workout_session(
            MagicMock(), user_id=OWNER_ID, workout_session_id=SESSION_ID
        )


def test_list_workout_sessions_checks_parent_week_ownership_first(monkeypatch):
    get_week_mock = MagicMock()
    monkeypatch.setattr(
        training_weeks_service, "get_owned_training_week", get_week_mock
    )
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "list_workout_sessions_for_week",
        lambda *a, **k: [],
    )
    session = MagicMock()

    workout_sessions_service.list_workout_sessions(
        session, user_id=OWNER_ID, week_id=WEEK_ID
    )

    get_week_mock.assert_called_once_with(session, user_id=OWNER_ID, week_id=WEEK_ID)


def test_list_workout_sessions_for_unowned_week_raises_week_not_found(monkeypatch):
    def _raise(*args, **kwargs):
        raise training_weeks_service.TrainingWeekNotFoundError(WEEK_ID)

    monkeypatch.setattr(training_weeks_service, "get_owned_training_week", _raise)

    with pytest.raises(training_weeks_service.TrainingWeekNotFoundError):
        workout_sessions_service.list_workout_sessions(
            MagicMock(), user_id=OWNER_ID, week_id=WEEK_ID
        )


def test_create_workout_session_with_no_order_index_assigns_zero_for_first_session(
    monkeypatch,
):
    monkeypatch.setattr(training_weeks_service, "get_owned_training_week", MagicMock())
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_max_order_index",
        lambda *a, **k: None,
    )
    create_mock = MagicMock(return_value=_session(order_index=0))
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "create_workout_session",
        create_mock,
    )

    workout_sessions_service.create_workout_session_for_week(
        MagicMock(),
        user_id=OWNER_ID,
        week_id=WEEK_ID,
        payload=WorkoutSessionCreate(day_name="Day A"),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["order_index"] == 0


def test_create_workout_session_with_no_order_index_assigns_max_plus_one(
    monkeypatch,
):
    monkeypatch.setattr(training_weeks_service, "get_owned_training_week", MagicMock())
    existing_max_order_index = 2
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_max_order_index",
        lambda *a, **k: existing_max_order_index,
    )
    create_mock = MagicMock(
        return_value=_session(order_index=existing_max_order_index + 1)
    )
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "create_workout_session",
        create_mock,
    )

    workout_sessions_service.create_workout_session_for_week(
        MagicMock(),
        user_id=OWNER_ID,
        week_id=WEEK_ID,
        payload=WorkoutSessionCreate(day_name="Day B"),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["order_index"] == existing_max_order_index + 1


def test_create_workout_session_with_explicit_order_index_uses_it(monkeypatch):
    monkeypatch.setattr(training_weeks_service, "get_owned_training_week", MagicMock())
    create_mock = MagicMock(return_value=_session(order_index=7))
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "create_workout_session",
        create_mock,
    )

    workout_sessions_service.create_workout_session_for_week(
        MagicMock(),
        user_id=OWNER_ID,
        week_id=WEEK_ID,
        payload=WorkoutSessionCreate(day_name="Day C", order_index=7),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["order_index"] == 7


def test_create_workout_session_for_unowned_week_raises_week_not_found(monkeypatch):
    def _raise(*args, **kwargs):
        raise training_weeks_service.TrainingWeekAccessDeniedError(WEEK_ID)

    monkeypatch.setattr(training_weeks_service, "get_owned_training_week", _raise)
    create_mock = MagicMock()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "create_workout_session",
        create_mock,
    )

    with pytest.raises(training_weeks_service.TrainingWeekAccessDeniedError):
        workout_sessions_service.create_workout_session_for_week(
            MagicMock(),
            user_id=OWNER_ID,
            week_id=WEEK_ID,
            payload=WorkoutSessionCreate(day_name="Day A"),
        )
    create_mock.assert_not_called()


def test_update_workout_session_applies_only_explicitly_set_fields(monkeypatch):
    workout_session = _session(day_name="Day A")
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_workout_session_with_owner",
        lambda *a, **k: (workout_session, OWNER_ID),
    )
    update_mock = MagicMock(side_effect=lambda session, ws, **fields: ws)
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "update_workout_session",
        update_mock,
    )
    payload = WorkoutSessionUpdate(order_index=3)

    workout_sessions_service.update_workout_session(
        MagicMock(), user_id=OWNER_ID, workout_session_id=SESSION_ID, payload=payload
    )

    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"order_index": 3}


def test_update_workout_session_with_no_fields_set_does_not_call_repo_update(
    monkeypatch,
):
    workout_session = _session()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_workout_session_with_owner",
        lambda *a, **k: (workout_session, OWNER_ID),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "update_workout_session",
        update_mock,
    )

    result = workout_sessions_service.update_workout_session(
        MagicMock(),
        user_id=OWNER_ID,
        workout_session_id=SESSION_ID,
        payload=WorkoutSessionUpdate(),
    )

    update_mock.assert_not_called()
    assert result is workout_session


def test_update_workout_session_for_other_users_session_raises_access_denied(
    monkeypatch,
):
    workout_session = _session()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_workout_session_with_owner",
        lambda *a, **k: (workout_session, OTHER_USER_ID),
    )

    with pytest.raises(workout_sessions_service.WorkoutSessionAccessDeniedError):
        workout_sessions_service.update_workout_session(
            MagicMock(),
            user_id=OWNER_ID,
            workout_session_id=SESSION_ID,
            payload=WorkoutSessionUpdate(order_index=1),
        )


def test_delete_workout_session_deletes_owned_session(monkeypatch):
    workout_session = _session()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_workout_session_with_owner",
        lambda *a, **k: (workout_session, OWNER_ID),
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "delete_workout_session",
        delete_mock,
    )

    workout_sessions_service.delete_workout_session(
        MagicMock(), user_id=OWNER_ID, workout_session_id=SESSION_ID
    )

    delete_mock.assert_called_once()
    assert delete_mock.call_args[0][1] is workout_session


def test_delete_workout_session_for_other_users_session_raises_access_denied(
    monkeypatch,
):
    workout_session = _session()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_workout_session_with_owner",
        lambda *a, **k: (workout_session, OTHER_USER_ID),
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "delete_workout_session",
        delete_mock,
    )

    with pytest.raises(workout_sessions_service.WorkoutSessionAccessDeniedError):
        workout_sessions_service.delete_workout_session(
            MagicMock(), user_id=OWNER_ID, workout_session_id=SESSION_ID
        )
    delete_mock.assert_not_called()


def test_update_workout_session_with_null_day_name_raises_invalid_update(monkeypatch):
    workout_session = _session(day_name="Day A")
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_workout_session_with_owner",
        lambda *a, **k: (workout_session, OWNER_ID),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "update_workout_session",
        update_mock,
    )
    payload = WorkoutSessionUpdate(day_name=None)

    with pytest.raises(workout_sessions_service.InvalidWorkoutSessionUpdateError):
        workout_sessions_service.update_workout_session(
            MagicMock(),
            user_id=OWNER_ID,
            workout_session_id=SESSION_ID,
            payload=payload,
        )
    update_mock.assert_not_called()


def test_update_workout_session_with_null_order_index_raises_invalid_update(
    monkeypatch,
):
    workout_session = _session()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "get_workout_session_with_owner",
        lambda *a, **k: (workout_session, OWNER_ID),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        workout_sessions_service.workout_sessions_repo,
        "update_workout_session",
        update_mock,
    )
    payload = WorkoutSessionUpdate(order_index=None)

    with pytest.raises(workout_sessions_service.InvalidWorkoutSessionUpdateError):
        workout_sessions_service.update_workout_session(
            MagicMock(),
            user_id=OWNER_ID,
            workout_session_id=SESSION_ID,
            payload=payload,
        )
    update_mock.assert_not_called()

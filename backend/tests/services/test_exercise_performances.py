"""Unit tests for app.services.exercise_performances.

The repository layer (and the parent prescription/session ownership checks) is
external I/O, so it's mocked here — these tests exercise ownership enforcement
and set_number auto-assignment that actually lives in the service.
"""

from unittest.mock import MagicMock

import pytest

from app.models.enums import SetCompletionState
from app.schemas.exercise_performances import (
    ExercisePerformanceCreate,
    ExercisePerformanceUpdate,
)
from app.services import exercise_performances as exercise_performances_service
from app.services import exercise_prescriptions as exercise_prescriptions_service
from app.services import workout_sessions as workout_sessions_service
from tests.factories import make_exercise_performance

OWNER_ID = 1
OTHER_USER_ID = 2
PRESCRIPTION_ID = 10
SESSION_ID = 20
PERFORMANCE_ID = 100


def _performance(**overrides) -> object:
    performance = make_exercise_performance(
        prescription_id=PRESCRIPTION_ID, **overrides
    )
    performance.id = PERFORMANCE_ID
    return performance


def _create_payload(**overrides) -> ExercisePerformanceCreate:
    data = {"actual_reps": 5, "completion_state": SetCompletionState.COMPLETED}
    data.update(overrides)
    return ExercisePerformanceCreate(**data)


def test_get_owned_exercise_performance_returns_performance_when_owned(monkeypatch):
    performance = _performance()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_exercise_performance_with_owner",
        lambda *a, **k: (performance, OWNER_ID),
    )

    result = exercise_performances_service.get_owned_exercise_performance(
        MagicMock(), user_id=OWNER_ID, performance_id=PERFORMANCE_ID
    )

    assert result is performance


def test_get_owned_exercise_performance_missing_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_exercise_performance_with_owner",
        lambda *a, **k: None,
    )

    with pytest.raises(exercise_performances_service.ExercisePerformanceNotFoundError):
        exercise_performances_service.get_owned_exercise_performance(
            MagicMock(), user_id=OWNER_ID, performance_id=PERFORMANCE_ID
        )


def test_get_owned_exercise_performance_belonging_to_other_user_raises_access_denied(
    monkeypatch,
):
    performance = _performance()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_exercise_performance_with_owner",
        lambda *a, **k: (performance, OTHER_USER_ID),
    )

    with pytest.raises(
        exercise_performances_service.ExercisePerformanceAccessDeniedError
    ):
        exercise_performances_service.get_owned_exercise_performance(
            MagicMock(), user_id=OWNER_ID, performance_id=PERFORMANCE_ID
        )


def test_list_performances_for_prescription_checks_parent_prescription_ownership_first(
    monkeypatch,
):
    get_prescription_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "get_owned_exercise_prescription",
        get_prescription_mock,
    )
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "list_performances_for_prescription",
        lambda *a, **k: [],
    )
    session = MagicMock()

    exercise_performances_service.list_performances_for_prescription(
        session, user_id=OWNER_ID, prescription_id=PRESCRIPTION_ID
    )

    get_prescription_mock.assert_called_once_with(
        session, user_id=OWNER_ID, prescription_id=PRESCRIPTION_ID
    )


def test_list_performances_for_unowned_prescription_raises_prescription_not_found(
    monkeypatch,
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExercisePrescriptionNotFoundError(
            PRESCRIPTION_ID
        )

    monkeypatch.setattr(
        exercise_prescriptions_service, "get_owned_exercise_prescription", _raise
    )

    with pytest.raises(
        exercise_prescriptions_service.ExercisePrescriptionNotFoundError
    ):
        exercise_performances_service.list_performances_for_prescription(
            MagicMock(), user_id=OWNER_ID, prescription_id=PRESCRIPTION_ID
        )


def test_list_performances_for_session_checks_parent_session_ownership_first(
    monkeypatch,
):
    get_session_mock = MagicMock()
    monkeypatch.setattr(
        workout_sessions_service, "get_owned_workout_session", get_session_mock
    )
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "list_performances_for_session",
        lambda *a, **k: [],
    )
    session = MagicMock()

    exercise_performances_service.list_performances_for_session(
        session, user_id=OWNER_ID, workout_session_id=SESSION_ID
    )

    get_session_mock.assert_called_once_with(
        session, user_id=OWNER_ID, workout_session_id=SESSION_ID
    )


def test_create_exercise_performance_with_no_set_number_assigns_one_for_first_set(
    monkeypatch,
):
    monkeypatch.setattr(
        exercise_prescriptions_service, "get_owned_exercise_prescription", MagicMock()
    )
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_max_set_number",
        lambda *a, **k: None,
    )
    create_mock = MagicMock(return_value=_performance(set_number=1))
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "create_exercise_performance",
        create_mock,
    )

    exercise_performances_service.create_exercise_performance_for_prescription(
        MagicMock(),
        user_id=OWNER_ID,
        prescription_id=PRESCRIPTION_ID,
        payload=_create_payload(),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["set_number"] == 1


def test_create_exercise_performance_with_no_set_number_assigns_max_plus_one(
    monkeypatch,
):
    monkeypatch.setattr(
        exercise_prescriptions_service, "get_owned_exercise_prescription", MagicMock()
    )
    existing_max_set_number = 3
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_max_set_number",
        lambda *a, **k: existing_max_set_number,
    )
    create_mock = MagicMock(
        return_value=_performance(set_number=existing_max_set_number + 1)
    )
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "create_exercise_performance",
        create_mock,
    )

    exercise_performances_service.create_exercise_performance_for_prescription(
        MagicMock(),
        user_id=OWNER_ID,
        prescription_id=PRESCRIPTION_ID,
        payload=_create_payload(),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["set_number"] == existing_max_set_number + 1


def test_create_exercise_performance_with_explicit_set_number_uses_it(monkeypatch):
    monkeypatch.setattr(
        exercise_prescriptions_service, "get_owned_exercise_prescription", MagicMock()
    )
    max_set_number_mock = MagicMock()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_max_set_number",
        max_set_number_mock,
    )
    create_mock = MagicMock(return_value=_performance(set_number=4))
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "create_exercise_performance",
        create_mock,
    )

    exercise_performances_service.create_exercise_performance_for_prescription(
        MagicMock(),
        user_id=OWNER_ID,
        prescription_id=PRESCRIPTION_ID,
        payload=_create_payload(set_number=4),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["set_number"] == 4
    max_set_number_mock.assert_not_called()


def test_create_exercise_performance_for_unowned_prescription_raises_not_found(
    monkeypatch,
):
    def _raise(*args, **kwargs):
        raise exercise_prescriptions_service.ExercisePrescriptionNotFoundError(
            PRESCRIPTION_ID
        )

    monkeypatch.setattr(
        exercise_prescriptions_service, "get_owned_exercise_prescription", _raise
    )
    create_mock = MagicMock()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "create_exercise_performance",
        create_mock,
    )

    with pytest.raises(
        exercise_prescriptions_service.ExercisePrescriptionNotFoundError
    ):
        exercise_performances_service.create_exercise_performance_for_prescription(
            MagicMock(),
            user_id=OWNER_ID,
            prescription_id=PRESCRIPTION_ID,
            payload=_create_payload(),
        )
    create_mock.assert_not_called()


def test_update_exercise_performance_applies_only_explicitly_set_fields(monkeypatch):
    performance = _performance(actual_reps=5)
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_exercise_performance_with_owner",
        lambda *a, **k: (performance, OWNER_ID),
    )
    update_mock = MagicMock(side_effect=lambda session, perf, **fields: perf)
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "update_exercise_performance",
        update_mock,
    )
    payload = ExercisePerformanceUpdate(actual_reps=3)

    exercise_performances_service.update_exercise_performance(
        MagicMock(),
        user_id=OWNER_ID,
        performance_id=PERFORMANCE_ID,
        payload=payload,
    )

    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"actual_reps": 3}


def test_update_exercise_performance_with_no_fields_set_does_not_call_repo_update(
    monkeypatch,
):
    performance = _performance()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_exercise_performance_with_owner",
        lambda *a, **k: (performance, OWNER_ID),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "update_exercise_performance",
        update_mock,
    )

    result = exercise_performances_service.update_exercise_performance(
        MagicMock(),
        user_id=OWNER_ID,
        performance_id=PERFORMANCE_ID,
        payload=ExercisePerformanceUpdate(),
    )

    update_mock.assert_not_called()
    assert result is performance


def test_update_exercise_performance_for_other_users_performance_raises_access_denied(
    monkeypatch,
):
    performance = _performance()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_exercise_performance_with_owner",
        lambda *a, **k: (performance, OTHER_USER_ID),
    )

    with pytest.raises(
        exercise_performances_service.ExercisePerformanceAccessDeniedError
    ):
        exercise_performances_service.update_exercise_performance(
            MagicMock(),
            user_id=OWNER_ID,
            performance_id=PERFORMANCE_ID,
            payload=ExercisePerformanceUpdate(actual_reps=3),
        )


def test_update_exercise_performance_with_null_actual_reps_raises_invalid_update(
    monkeypatch,
):
    performance = _performance()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_exercise_performance_with_owner",
        lambda *a, **k: (performance, OWNER_ID),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "update_exercise_performance",
        update_mock,
    )
    payload = ExercisePerformanceUpdate(actual_reps=None)

    with pytest.raises(
        exercise_performances_service.InvalidExercisePerformanceUpdateError
    ):
        exercise_performances_service.update_exercise_performance(
            MagicMock(),
            user_id=OWNER_ID,
            performance_id=PERFORMANCE_ID,
            payload=payload,
        )
    update_mock.assert_not_called()


def test_update_exercise_performance_with_null_actual_weight_proceeds_normally(
    monkeypatch,
):
    # actual_weight is genuinely nullable (bodyweight work) — clearing it must
    # not be rejected by the same guard that blocks a null actual_reps/
    # set_number/completion_state.
    performance = _performance(actual_weight=100.0)
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_exercise_performance_with_owner",
        lambda *a, **k: (performance, OWNER_ID),
    )
    update_mock = MagicMock(side_effect=lambda session, perf, **fields: perf)
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "update_exercise_performance",
        update_mock,
    )
    payload = ExercisePerformanceUpdate(actual_weight=None)

    exercise_performances_service.update_exercise_performance(
        MagicMock(),
        user_id=OWNER_ID,
        performance_id=PERFORMANCE_ID,
        payload=payload,
    )

    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"actual_weight": None}


def test_delete_exercise_performance_deletes_owned_performance(monkeypatch):
    performance = _performance()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_exercise_performance_with_owner",
        lambda *a, **k: (performance, OWNER_ID),
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "delete_exercise_performance",
        delete_mock,
    )

    exercise_performances_service.delete_exercise_performance(
        MagicMock(), user_id=OWNER_ID, performance_id=PERFORMANCE_ID
    )

    delete_mock.assert_called_once()
    assert delete_mock.call_args[0][1] is performance


def test_delete_exercise_performance_for_other_users_performance_raises_access_denied(
    monkeypatch,
):
    performance = _performance()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "get_exercise_performance_with_owner",
        lambda *a, **k: (performance, OTHER_USER_ID),
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(
        exercise_performances_service.exercise_performances_repo,
        "delete_exercise_performance",
        delete_mock,
    )

    with pytest.raises(
        exercise_performances_service.ExercisePerformanceAccessDeniedError
    ):
        exercise_performances_service.delete_exercise_performance(
            MagicMock(), user_id=OWNER_ID, performance_id=PERFORMANCE_ID
        )
    delete_mock.assert_not_called()

"""Unit tests for app.services.exercise_prescriptions.

The repository layer (the parent WorkoutSession ownership check, and the exercise
visibility lookup) is external I/O, so it's mocked here — these tests exercise
ownership enforcement, order_index auto-assignment, and exercise-visibility
validation that actually lives in the service.
"""

from unittest.mock import MagicMock

import pytest

from app.schemas.exercise_prescriptions import (
    ExercisePrescriptionCreate,
    ExercisePrescriptionUpdate,
)
from app.schemas.progression import ProgressionParams
from app.services import exercise_prescriptions as exercise_prescriptions_service
from app.services import workout_sessions as workout_sessions_service
from tests.factories import make_exercise, make_exercise_prescription

OWNER_ID = 1
OTHER_USER_ID = 2
SESSION_ID = 10
EXERCISE_ID = 50
PRESCRIPTION_ID = 100


def _prescription(**overrides) -> object:
    prescription = make_exercise_prescription(
        workout_session_id=SESSION_ID, exercise_id=EXERCISE_ID, **overrides
    )
    prescription.id = PRESCRIPTION_ID
    return prescription


def _create_payload(**overrides) -> ExercisePrescriptionCreate:
    data = {"exercise_id": EXERCISE_ID, "target_sets": 5, "target_reps": 5}
    data.update(overrides)
    return ExercisePrescriptionCreate(**data)


def test_get_owned_exercise_prescription_returns_prescription_when_owned(
    monkeypatch,
):
    prescription = _prescription()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )

    result = exercise_prescriptions_service.get_owned_exercise_prescription(
        MagicMock(), user_id=OWNER_ID, prescription_id=PRESCRIPTION_ID
    )

    assert result is prescription


def test_get_owned_exercise_prescription_missing_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: None,
    )

    with pytest.raises(
        exercise_prescriptions_service.ExercisePrescriptionNotFoundError
    ):
        exercise_prescriptions_service.get_owned_exercise_prescription(
            MagicMock(), user_id=OWNER_ID, prescription_id=PRESCRIPTION_ID
        )


def test_get_owned_exercise_prescription_belonging_to_other_user_raises_access_denied(
    monkeypatch,
):
    prescription = _prescription()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OTHER_USER_ID),
    )

    with pytest.raises(
        exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError
    ):
        exercise_prescriptions_service.get_owned_exercise_prescription(
            MagicMock(), user_id=OWNER_ID, prescription_id=PRESCRIPTION_ID
        )


def test_list_exercise_prescriptions_checks_parent_session_ownership_first(
    monkeypatch,
):
    get_session_mock = MagicMock()
    monkeypatch.setattr(
        workout_sessions_service, "get_owned_workout_session", get_session_mock
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "list_exercise_prescriptions_for_session",
        lambda *a, **k: [],
    )
    session = MagicMock()

    exercise_prescriptions_service.list_exercise_prescriptions(
        session, user_id=OWNER_ID, workout_session_id=SESSION_ID
    )

    get_session_mock.assert_called_once_with(
        session, user_id=OWNER_ID, workout_session_id=SESSION_ID
    )


def test_create_exercise_prescription_with_visible_exercise_succeeds(monkeypatch):
    monkeypatch.setattr(
        workout_sessions_service, "get_owned_workout_session", MagicMock()
    )
    exercise = make_exercise()
    exercise.id = EXERCISE_ID
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: exercise,
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_max_order_index",
        lambda *a, **k: None,
    )
    create_mock = MagicMock(return_value=_prescription())
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "create_exercise_prescription",
        create_mock,
    )

    result = exercise_prescriptions_service.create_exercise_prescription_for_session(
        MagicMock(),
        user_id=OWNER_ID,
        workout_session_id=SESSION_ID,
        payload=_create_payload(),
    )

    assert result is create_mock.return_value


def test_create_exercise_prescription_dumps_progression_params_to_a_plain_dict(
    monkeypatch,
):
    # The real break risk flagged in TRAIN-20's design plan: SQLModel won't
    # serialize a ProgressionParams instance into the JSONB column, so the
    # repository must receive a plain dict, not the Pydantic model.
    monkeypatch.setattr(
        workout_sessions_service, "get_owned_workout_session", MagicMock()
    )
    exercise = make_exercise()
    exercise.id = EXERCISE_ID
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: exercise,
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_max_order_index",
        lambda *a, **k: None,
    )
    create_mock = MagicMock(return_value=_prescription())
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "create_exercise_prescription",
        create_mock,
    )
    payload = _create_payload(progression_params=ProgressionParams(increment=5.0))

    exercise_prescriptions_service.create_exercise_prescription_for_session(
        MagicMock(),
        user_id=OWNER_ID,
        workout_session_id=SESSION_ID,
        payload=payload,
    )

    _, called_kwargs = create_mock.call_args
    dumped = called_kwargs["progression_params"]
    assert dumped == {"increment": 5.0}
    assert type(dumped) is dict


def test_create_exercise_prescription_with_invisible_exercise_raises_not_visible(
    monkeypatch,
):
    monkeypatch.setattr(
        workout_sessions_service, "get_owned_workout_session", MagicMock()
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: None,
    )
    create_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "create_exercise_prescription",
        create_mock,
    )

    with pytest.raises(exercise_prescriptions_service.ExerciseNotVisibleError):
        exercise_prescriptions_service.create_exercise_prescription_for_session(
            MagicMock(),
            user_id=OWNER_ID,
            workout_session_id=SESSION_ID,
            payload=_create_payload(),
        )
    create_mock.assert_not_called()


def test_create_exercise_prescription_with_no_order_index_assigns_zero_for_first(
    monkeypatch,
):
    monkeypatch.setattr(
        workout_sessions_service, "get_owned_workout_session", MagicMock()
    )
    exercise = make_exercise()
    exercise.id = EXERCISE_ID
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: exercise,
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_max_order_index",
        lambda *a, **k: None,
    )
    create_mock = MagicMock(return_value=_prescription(order_index=0))
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "create_exercise_prescription",
        create_mock,
    )

    exercise_prescriptions_service.create_exercise_prescription_for_session(
        MagicMock(),
        user_id=OWNER_ID,
        workout_session_id=SESSION_ID,
        payload=_create_payload(),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["order_index"] == 0


def test_create_exercise_prescription_with_no_order_index_assigns_max_plus_one(
    monkeypatch,
):
    monkeypatch.setattr(
        workout_sessions_service, "get_owned_workout_session", MagicMock()
    )
    exercise = make_exercise()
    exercise.id = EXERCISE_ID
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: exercise,
    )
    existing_max_order_index = 4
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_max_order_index",
        lambda *a, **k: existing_max_order_index,
    )
    create_mock = MagicMock(
        return_value=_prescription(order_index=existing_max_order_index + 1)
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "create_exercise_prescription",
        create_mock,
    )

    exercise_prescriptions_service.create_exercise_prescription_for_session(
        MagicMock(),
        user_id=OWNER_ID,
        workout_session_id=SESSION_ID,
        payload=_create_payload(),
    )

    _, called_kwargs = create_mock.call_args
    assert called_kwargs["order_index"] == existing_max_order_index + 1


def test_create_exercise_prescription_for_unowned_session_raises_session_not_found(
    monkeypatch,
):
    def _raise(*args, **kwargs):
        raise workout_sessions_service.WorkoutSessionNotFoundError(SESSION_ID)

    monkeypatch.setattr(workout_sessions_service, "get_owned_workout_session", _raise)
    visible_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        visible_mock,
    )

    with pytest.raises(workout_sessions_service.WorkoutSessionNotFoundError):
        exercise_prescriptions_service.create_exercise_prescription_for_session(
            MagicMock(),
            user_id=OWNER_ID,
            workout_session_id=SESSION_ID,
            payload=_create_payload(),
        )
    # Parent ownership is checked before the exercise-visibility lookup runs.
    visible_mock.assert_not_called()


def test_update_exercise_prescription_applies_only_explicitly_set_fields(
    monkeypatch,
):
    prescription = _prescription(target_sets=5)
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    update_mock = MagicMock(side_effect=lambda session, rx, **fields: rx)
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription",
        update_mock,
    )
    payload = ExercisePrescriptionUpdate(target_sets=3)

    exercise_prescriptions_service.update_exercise_prescription(
        MagicMock(),
        user_id=OWNER_ID,
        prescription_id=PRESCRIPTION_ID,
        payload=payload,
    )

    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"target_sets": 3}


def test_update_exercise_prescription_dumps_progression_params_to_a_plain_dict(
    monkeypatch,
):
    prescription = _prescription()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    update_mock = MagicMock(side_effect=lambda session, rx, **fields: rx)
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription",
        update_mock,
    )
    payload = ExercisePrescriptionUpdate(
        progression_params=ProgressionParams(percentage=0.03)
    )

    exercise_prescriptions_service.update_exercise_prescription(
        MagicMock(),
        user_id=OWNER_ID,
        prescription_id=PRESCRIPTION_ID,
        payload=payload,
    )

    _, called_kwargs = update_mock.call_args
    dumped = called_kwargs["progression_params"]
    assert dumped == {"percentage": 0.03}
    assert type(dumped) is dict


def test_update_exercise_prescription_with_no_fields_set_does_not_call_repo_update(
    monkeypatch,
):
    prescription = _prescription()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription",
        update_mock,
    )

    result = exercise_prescriptions_service.update_exercise_prescription(
        MagicMock(),
        user_id=OWNER_ID,
        prescription_id=PRESCRIPTION_ID,
        payload=ExercisePrescriptionUpdate(),
    )

    update_mock.assert_not_called()
    assert result is prescription


def test_update_exercise_prescription_changing_exercise_id_revalidates_visibility(
    monkeypatch,
):
    prescription = _prescription()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    new_exercise_id = EXERCISE_ID + 1
    new_exercise = make_exercise()
    new_exercise.id = new_exercise_id
    visible_mock = MagicMock(return_value=new_exercise)
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        visible_mock,
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription",
        MagicMock(side_effect=lambda session, rx, **fields: rx),
    )

    exercise_prescriptions_service.update_exercise_prescription(
        MagicMock(),
        user_id=OWNER_ID,
        prescription_id=PRESCRIPTION_ID,
        payload=ExercisePrescriptionUpdate(exercise_id=new_exercise_id),
    )

    _, called_kwargs = visible_mock.call_args
    assert called_kwargs["exercise_id"] == new_exercise_id


def test_update_exercise_prescription_to_an_invisible_exercise_raises_not_visible(
    monkeypatch,
):
    prescription = _prescription()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: None,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription",
        update_mock,
    )

    with pytest.raises(exercise_prescriptions_service.ExerciseNotVisibleError):
        exercise_prescriptions_service.update_exercise_prescription(
            MagicMock(),
            user_id=OWNER_ID,
            prescription_id=PRESCRIPTION_ID,
            payload=ExercisePrescriptionUpdate(exercise_id=EXERCISE_ID + 1),
        )
    update_mock.assert_not_called()


def test_update_exercise_prescription_without_changing_exercise_id_skips_visibility_check(
    monkeypatch,
):
    prescription = _prescription()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    visible_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        visible_mock,
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription",
        MagicMock(side_effect=lambda session, rx, **fields: rx),
    )

    exercise_prescriptions_service.update_exercise_prescription(
        MagicMock(),
        user_id=OWNER_ID,
        prescription_id=PRESCRIPTION_ID,
        payload=ExercisePrescriptionUpdate(target_sets=8),
    )

    visible_mock.assert_not_called()


def test_delete_exercise_prescription_deletes_owned_prescription(monkeypatch):
    prescription = _prescription()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "delete_exercise_prescription",
        delete_mock,
    )

    exercise_prescriptions_service.delete_exercise_prescription(
        MagicMock(), user_id=OWNER_ID, prescription_id=PRESCRIPTION_ID
    )

    delete_mock.assert_called_once()
    assert delete_mock.call_args[0][1] is prescription


def test_delete_exercise_prescription_for_other_users_prescription_raises_access_denied(
    monkeypatch,
):
    prescription = _prescription()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OTHER_USER_ID),
    )
    delete_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "delete_exercise_prescription",
        delete_mock,
    )

    with pytest.raises(
        exercise_prescriptions_service.ExercisePrescriptionAccessDeniedError
    ):
        exercise_prescriptions_service.delete_exercise_prescription(
            MagicMock(), user_id=OWNER_ID, prescription_id=PRESCRIPTION_ID
        )
    delete_mock.assert_not_called()


def test_update_exercise_prescription_with_null_exercise_id_raises_invalid_update(
    monkeypatch,
):
    prescription = _prescription()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    visible_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        visible_mock,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription",
        update_mock,
    )
    payload = ExercisePrescriptionUpdate(exercise_id=None)

    with pytest.raises(
        exercise_prescriptions_service.InvalidExercisePrescriptionUpdateError
    ):
        exercise_prescriptions_service.update_exercise_prescription(
            MagicMock(),
            user_id=OWNER_ID,
            prescription_id=PRESCRIPTION_ID,
            payload=payload,
        )
    # A null exercise_id is rejected before it ever reaches the visibility
    # lookup or the repository update.
    visible_mock.assert_not_called()
    update_mock.assert_not_called()


def test_update_exercise_prescription_with_null_target_weight_proceeds_normally(
    monkeypatch,
):
    # target_weight is genuinely nullable — explicitly clearing it must not be
    # rejected by the same guard that blocks a null exercise_id/order_index/
    # target_sets/target_reps.
    prescription = _prescription(target_weight=100.0)
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    update_mock = MagicMock(side_effect=lambda session, rx, **fields: rx)
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription",
        update_mock,
    )
    payload = ExercisePrescriptionUpdate(target_weight=None)

    exercise_prescriptions_service.update_exercise_prescription(
        MagicMock(),
        user_id=OWNER_ID,
        prescription_id=PRESCRIPTION_ID,
        payload=payload,
    )

    _, called_kwargs = update_mock.call_args
    assert called_kwargs == {"target_weight": None}

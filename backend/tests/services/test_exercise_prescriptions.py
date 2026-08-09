"""Unit tests for app.services.exercise_prescriptions.

The repository layer (the parent WorkoutSession ownership check, and the exercise
visibility lookup) is external I/O, so it's mocked here — these tests exercise
ownership enforcement, order_index auto-assignment, and exercise-visibility
validation that actually lives in the service.
"""

from unittest.mock import MagicMock

import pytest

from app.models.progression_line import ProgressionLine
from app.schemas.exercise_prescriptions import (
    ExercisePrescriptionCreate,
    ExercisePrescriptionUpdate,
)
from app.schemas.progression import ProgressionParams
from app.schemas.progression_lines import ProgressionLineCreateRequest
from app.services import exercise_prescriptions as exercise_prescriptions_service
from app.services import workout_sessions as workout_sessions_service
from tests.factories import (
    make_exercise,
    make_exercise_prescription,
    make_progression_line,
)

OWNER_ID = 1
OTHER_USER_ID = 2
PROGRAM_ID = 5
SESSION_ID = 10
EXERCISE_ID = 50
OTHER_EXERCISE_ID = 51
PRESCRIPTION_ID = 100
PROGRESSION_LINE_ID = 200
OTHER_PROGRESSION_LINE_ID = 201


def _prescription(**overrides) -> object:
    data = {
        "workout_session_id": SESSION_ID,
        "exercise_id": EXERCISE_ID,
        "progression_line_id": PROGRESSION_LINE_ID,
    }
    data.update(overrides)
    prescription = make_exercise_prescription(**data)
    prescription.id = PRESCRIPTION_ID
    return prescription


def _prescription_on_line(line: ProgressionLine, **overrides) -> object:
    """Like `_prescription`, but also stubs the `workout_session` relationship
    (`.week.program_id`) that `update_exercise_prescription`'s exercise_id-change
    branch reads to resolve the new exercise's default line — a transient
    (unpersisted) model has no session to lazily load that relationship from, so
    it must be stubbed explicitly rather than left to resolve to `None`.
    """
    prescription = _prescription(progression_line_id=line.id, **overrides)
    prescription.workout_session = MagicMock(week=MagicMock(program_id=PROGRAM_ID))
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
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "resolve_progression_line_for_new_prescription",
        lambda *a, **k: make_progression_line(
            program_id=PROGRAM_ID, exercise_id=EXERCISE_ID, id=PROGRESSION_LINE_ID
        ),
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
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "resolve_progression_line_for_new_prescription",
        lambda *a, **k: make_progression_line(
            program_id=PROGRAM_ID, exercise_id=EXERCISE_ID, id=PROGRESSION_LINE_ID
        ),
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
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "resolve_progression_line_for_new_prescription",
        lambda *a, **k: make_progression_line(
            program_id=PROGRAM_ID, exercise_id=EXERCISE_ID, id=PROGRESSION_LINE_ID
        ),
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
    monkeypatch.setattr(
        exercise_prescriptions_service,
        "resolve_progression_line_for_new_prescription",
        lambda *a, **k: make_progression_line(
            program_id=PROGRAM_ID, exercise_id=EXERCISE_ID, id=PROGRESSION_LINE_ID
        ),
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
    default_line = make_progression_line(
        program_id=PROGRAM_ID, exercise_id=EXERCISE_ID, id=PROGRESSION_LINE_ID
    )
    prescription = _prescription_on_line(default_line)
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
        exercise_prescriptions_service.progression_lines_repo,
        "get_progression_line",
        lambda *a, **k: default_line,
    )
    new_default_line = make_progression_line(
        program_id=PROGRAM_ID,
        exercise_id=new_exercise_id,
        id=OTHER_PROGRESSION_LINE_ID,
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.progression_lines_repo,
        "get_default_progression_line",
        lambda *a, **k: new_default_line,
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription_with_progression_line",
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


def test_update_exercise_prescription_changing_exercise_id_on_default_line_reresolves_to_new_default_line(
    monkeypatch,
):
    default_line = make_progression_line(
        program_id=PROGRAM_ID, exercise_id=EXERCISE_ID, id=PROGRESSION_LINE_ID
    )
    prescription = _prescription_on_line(default_line)
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    new_exercise_id = EXERCISE_ID + 1
    new_exercise = make_exercise()
    new_exercise.id = new_exercise_id
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: new_exercise,
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.progression_lines_repo,
        "get_progression_line",
        lambda *a, **k: default_line,
    )
    new_default_line = make_progression_line(
        program_id=PROGRAM_ID,
        exercise_id=new_exercise_id,
        id=OTHER_PROGRESSION_LINE_ID,
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.progression_lines_repo,
        "get_default_progression_line",
        lambda *a, **k: new_default_line,
    )
    move_mock = MagicMock(side_effect=lambda session, rx, **fields: rx)
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription_with_progression_line",
        move_mock,
    )

    exercise_prescriptions_service.update_exercise_prescription(
        MagicMock(),
        user_id=OWNER_ID,
        prescription_id=PRESCRIPTION_ID,
        payload=ExercisePrescriptionUpdate(exercise_id=new_exercise_id),
    )

    # Single-commit write: both the new exercise_id and the re-resolved default
    # line's id must land in the same update_exercise_prescription_with_
    # progression_line call — see that function's docstring for why two separate
    # commits would leave a corruptible window.
    _, called_kwargs = move_mock.call_args
    assert called_kwargs["progression_line_id"] == new_default_line.id
    assert called_kwargs["exercise_id"] == new_exercise_id


def test_update_exercise_prescription_changing_exercise_id_on_explicit_line_raises_invalid_update(
    monkeypatch,
):
    explicit_line = make_progression_line(
        program_id=PROGRAM_ID,
        exercise_id=EXERCISE_ID,
        id=OTHER_PROGRESSION_LINE_ID,
        is_default=False,
        label="Light",
    )
    prescription = _prescription_on_line(explicit_line)
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "get_exercise_prescription_with_owner",
        lambda *a, **k: (prescription, OWNER_ID),
    )
    new_exercise = make_exercise()
    new_exercise.id = EXERCISE_ID + 1
    monkeypatch.setattr(
        exercise_prescriptions_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: new_exercise,
    )
    monkeypatch.setattr(
        exercise_prescriptions_service.progression_lines_repo,
        "get_progression_line",
        lambda *a, **k: explicit_line,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(
        exercise_prescriptions_service.exercise_prescriptions_repo,
        "update_exercise_prescription",
        update_mock,
    )

    with pytest.raises(
        exercise_prescriptions_service.InvalidExercisePrescriptionUpdateError
    ):
        exercise_prescriptions_service.update_exercise_prescription(
            MagicMock(),
            user_id=OWNER_ID,
            prescription_id=PRESCRIPTION_ID,
            payload=ExercisePrescriptionUpdate(exercise_id=EXERCISE_ID + 1),
        )
    update_mock.assert_not_called()


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


class TestResolveProgressionLineForNewPrescription:
    """`resolve_progression_line_for_new_prescription`'s three branches — the
    exact create-payload shapes TRAIN-26's AC requires: neither field set,
    an existing progression_line_id, or a request to start a new line — plus
    the cross-program/cross-exercise reference checks that keep another
    program's (or exercise's) line id from being attached.
    """

    def test_neither_field_set_finds_the_existing_default_line(self, monkeypatch):
        default_line = make_progression_line(
            program_id=PROGRAM_ID, exercise_id=EXERCISE_ID, id=PROGRESSION_LINE_ID
        )
        create_mock = MagicMock()
        monkeypatch.setattr(
            exercise_prescriptions_service.progression_lines_repo,
            "get_default_progression_line",
            lambda *a, **k: default_line,
        )
        monkeypatch.setattr(
            exercise_prescriptions_service.progression_lines_repo,
            "create_progression_line",
            create_mock,
        )

        line = exercise_prescriptions_service.resolve_progression_line_for_new_prescription(
            MagicMock(),
            program_id=PROGRAM_ID,
            exercise_id=EXERCISE_ID,
            progression_line_id=None,
            start_new_progression_line_label=None,
            starting_new_line=False,
        )

        assert line is default_line
        create_mock.assert_not_called()

    def test_neither_field_set_creates_the_default_line_when_none_exists(
        self, monkeypatch
    ):
        created_line = make_progression_line(
            program_id=PROGRAM_ID, exercise_id=EXERCISE_ID, id=PROGRESSION_LINE_ID
        )
        monkeypatch.setattr(
            exercise_prescriptions_service.progression_lines_repo,
            "get_default_progression_line",
            lambda *a, **k: None,
        )
        create_mock = MagicMock(return_value=created_line)
        monkeypatch.setattr(
            exercise_prescriptions_service.progression_lines_repo,
            "create_progression_line",
            create_mock,
        )

        line = exercise_prescriptions_service.resolve_progression_line_for_new_prescription(
            MagicMock(),
            program_id=PROGRAM_ID,
            exercise_id=EXERCISE_ID,
            progression_line_id=None,
            start_new_progression_line_label=None,
            starting_new_line=False,
        )

        assert line is created_line
        _, called_kwargs = create_mock.call_args
        assert called_kwargs["is_default"] is True
        assert called_kwargs["label"] is None

    def test_progression_line_id_set_continues_the_existing_line(self, monkeypatch):
        explicit_line = make_progression_line(
            program_id=PROGRAM_ID,
            exercise_id=EXERCISE_ID,
            id=OTHER_PROGRESSION_LINE_ID,
            is_default=False,
            label="Light",
        )
        monkeypatch.setattr(
            exercise_prescriptions_service.progression_lines_repo,
            "get_progression_line",
            lambda *a, **k: explicit_line,
        )

        line = exercise_prescriptions_service.resolve_progression_line_for_new_prescription(
            MagicMock(),
            program_id=PROGRAM_ID,
            exercise_id=EXERCISE_ID,
            progression_line_id=OTHER_PROGRESSION_LINE_ID,
            start_new_progression_line_label=None,
            starting_new_line=False,
        )

        assert line is explicit_line

    def test_progression_line_id_that_does_not_exist_raises_invalid_reference(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            exercise_prescriptions_service.progression_lines_repo,
            "get_progression_line",
            lambda *a, **k: None,
        )

        with pytest.raises(
            exercise_prescriptions_service.InvalidProgressionLineReferenceError
        ):
            exercise_prescriptions_service.resolve_progression_line_for_new_prescription(
                MagicMock(),
                program_id=PROGRAM_ID,
                exercise_id=EXERCISE_ID,
                progression_line_id=OTHER_PROGRESSION_LINE_ID,
                start_new_progression_line_label=None,
                starting_new_line=False,
            )

    def test_progression_line_id_from_a_different_program_raises_invalid_reference(
        self, monkeypatch
    ):
        other_programs_line = make_progression_line(
            program_id=PROGRAM_ID + 1,
            exercise_id=EXERCISE_ID,
            id=OTHER_PROGRESSION_LINE_ID,
        )
        monkeypatch.setattr(
            exercise_prescriptions_service.progression_lines_repo,
            "get_progression_line",
            lambda *a, **k: other_programs_line,
        )

        with pytest.raises(
            exercise_prescriptions_service.InvalidProgressionLineReferenceError
        ):
            exercise_prescriptions_service.resolve_progression_line_for_new_prescription(
                MagicMock(),
                program_id=PROGRAM_ID,
                exercise_id=EXERCISE_ID,
                progression_line_id=OTHER_PROGRESSION_LINE_ID,
                start_new_progression_line_label=None,
                starting_new_line=False,
            )

    def test_progression_line_id_for_a_different_exercise_raises_invalid_reference(
        self, monkeypatch
    ):
        other_exercises_line = make_progression_line(
            program_id=PROGRAM_ID,
            exercise_id=OTHER_EXERCISE_ID,
            id=OTHER_PROGRESSION_LINE_ID,
        )
        monkeypatch.setattr(
            exercise_prescriptions_service.progression_lines_repo,
            "get_progression_line",
            lambda *a, **k: other_exercises_line,
        )

        with pytest.raises(
            exercise_prescriptions_service.InvalidProgressionLineReferenceError
        ):
            exercise_prescriptions_service.resolve_progression_line_for_new_prescription(
                MagicMock(),
                program_id=PROGRAM_ID,
                exercise_id=EXERCISE_ID,
                progression_line_id=OTHER_PROGRESSION_LINE_ID,
                start_new_progression_line_label=None,
                starting_new_line=False,
            )

    def test_start_new_progression_line_creates_a_non_default_line(self, monkeypatch):
        created_line = make_progression_line(
            program_id=PROGRAM_ID,
            exercise_id=EXERCISE_ID,
            id=OTHER_PROGRESSION_LINE_ID,
            is_default=False,
            label="Light",
        )
        create_mock = MagicMock(return_value=created_line)
        monkeypatch.setattr(
            exercise_prescriptions_service.progression_lines_repo,
            "create_progression_line",
            create_mock,
        )

        line = exercise_prescriptions_service.resolve_progression_line_for_new_prescription(
            MagicMock(),
            program_id=PROGRAM_ID,
            exercise_id=EXERCISE_ID,
            progression_line_id=None,
            start_new_progression_line_label="Light",
            starting_new_line=True,
        )

        assert line is created_line
        _, called_kwargs = create_mock.call_args
        assert called_kwargs["is_default"] is False
        assert called_kwargs["label"] == "Light"


class TestExercisePrescriptionCreateSchemaProgressionLineExclusivity:
    """The mutual-exclusivity guard between `progression_line_id` and
    `start_new_progression_line` — enforced by the Pydantic schema itself, not
    the service, so it's exercised directly against the schema here.
    """

    def test_both_progression_line_fields_set_raises_value_error(self):
        with pytest.raises(ValueError):
            ExercisePrescriptionCreate(
                exercise_id=EXERCISE_ID,
                target_sets=5,
                target_reps=5,
                progression_line_id=PROGRESSION_LINE_ID,
                start_new_progression_line=ProgressionLineCreateRequest(label="Light"),
            )

"""Unit tests for app.services.history.

Pure core (estimate_one_rm, to_kg/from_kg, best_effort, detect_new_records) is
tested directly with fixed inputs, per TRAIN-21's acceptance criterion. The
orchestration functions mock the repository/service collaborators (external
I/O) and exercise ownership checks + reduction wiring.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.enums import PersonalRecordKind, WeightUnit
from app.services import history as history_service

USER_ID = 1
EXERCISE_ID = 20
PROGRAM_ID = 3
SESSION_ID = 42
LINE_ID = 7


def _performed_at(days_ago: int = 0) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) - timedelta(days=days_ago)


def _row(
    *,
    weight: float,
    reps: int,
    unit: WeightUnit = WeightUnit.KG,
    performed_at: datetime | None = None,
    workout_session_id: int = SESSION_ID,
    program_id: int = PROGRAM_ID,
    progression_line_id: int = LINE_ID,
) -> tuple:
    return (
        weight,
        reps,
        unit,
        performed_at or _performed_at(),
        workout_session_id,
        program_id,
        progression_line_id,
    )


def _record(**overrides) -> history_service.PerformanceRecord:
    data = {
        "weight": 100.0,
        "reps": 5,
        "weight_unit": WeightUnit.KG,
        "performed_at": _performed_at(),
        "workout_session_id": SESSION_ID,
        "program_id": PROGRAM_ID,
        "progression_line_id": LINE_ID,
    }
    data.update(overrides)
    return history_service.PerformanceRecord(**data)


# --------------------------------------------------------------------------
# estimate_one_rm
# --------------------------------------------------------------------------


def test_estimate_one_rm_uses_epley_formula_for_multiple_reps():
    weight, reps = 100.0, 5

    result = history_service.estimate_one_rm(weight, reps)

    assert result == weight * (1 + reps / 30)


def test_estimate_one_rm_for_a_single_rep_returns_weight_unchanged():
    weight = 140.0

    result = history_service.estimate_one_rm(weight, 1)

    assert result == weight


def test_estimate_one_rm_for_zero_reps_returns_none():
    assert history_service.estimate_one_rm(100.0, 0) is None


def test_estimate_one_rm_for_negative_reps_returns_none():
    assert history_service.estimate_one_rm(100.0, -1) is None


# --------------------------------------------------------------------------
# to_kg / from_kg
# --------------------------------------------------------------------------


def test_to_kg_for_kg_input_is_a_no_op():
    weight = 137.5

    assert history_service.to_kg(weight, WeightUnit.KG) == weight


def test_to_kg_for_lb_input_converts_using_the_avoirdupois_pound():
    weight_lb = 300.0

    result = history_service.to_kg(weight_lb, WeightUnit.LB)

    assert result == weight_lb * history_service._LB_TO_KG


def test_from_kg_for_lb_display_divides_rather_than_multiplies_by_reciprocal():
    weight_kg = 137.5

    result = history_service.from_kg(weight_kg, WeightUnit.LB)

    assert result == weight_kg / history_service._LB_TO_KG


def test_estimate_one_rm_is_linear_so_unit_conversion_order_does_not_matter():
    weight_lb, reps = 300.0, 5

    convert_then_estimate = history_service.estimate_one_rm(
        history_service.to_kg(weight_lb, WeightUnit.LB), reps
    )
    estimate_then_convert = history_service.to_kg(
        history_service.estimate_one_rm(weight_lb, reps), WeightUnit.LB
    )

    assert convert_then_estimate == pytest.approx(estimate_then_convert)


# --------------------------------------------------------------------------
# best_effort
# --------------------------------------------------------------------------


def test_best_effort_for_empty_records_returns_none():
    assert history_service.best_effort([]) is None


def test_best_effort_picks_the_heaviest_weight_and_the_highest_e1rm_separately():
    heavy_single = _record(weight=180.0, reps=1)
    light_high_rep_volume_set = _record(weight=140.0, reps=10)

    result = history_service.best_effort([heavy_single, light_high_rep_volume_set])

    assert result.best_weight.weight == heavy_single.weight
    assert result.best_one_rm.one_rm == history_service.estimate_one_rm(
        light_high_rep_volume_set.weight, light_high_rep_volume_set.reps
    )


def test_best_effort_across_units_compares_by_kg_not_the_logged_value():
    heavier_in_kg = _record(weight=100.0, reps=1, weight_unit=WeightUnit.KG)
    lighter_but_larger_number_in_lb = _record(
        weight=150.0, reps=1, weight_unit=WeightUnit.LB
    )

    result = history_service.best_effort(
        [heavier_in_kg, lighter_but_larger_number_in_lb]
    )

    assert result.best_weight.weight == heavier_in_kg.weight
    assert result.best_weight.weight_unit == WeightUnit.KG


def test_best_effort_on_a_tied_weight_picks_the_earliest_occurrence():
    earlier_hit = _record(
        weight=140.0,
        reps=1,
        performed_at=_performed_at(days_ago=30),
        workout_session_id=1,
    )
    later_repeat = _record(
        weight=140.0,
        reps=1,
        performed_at=_performed_at(days_ago=0),
        workout_session_id=2,
    )

    result_in_chronological_order = history_service.best_effort(
        [earlier_hit, later_repeat]
    )
    result_in_reverse_order = history_service.best_effort([later_repeat, earlier_hit])

    for result in (result_in_chronological_order, result_in_reverse_order):
        assert result.best_weight.workout_session_id == earlier_hit.workout_session_id
        assert result.best_weight.performed_at == earlier_hit.performed_at


# --------------------------------------------------------------------------
# detect_new_records
# --------------------------------------------------------------------------


def test_detect_new_records_with_no_prior_best_reports_everything_as_a_record():
    session_best = history_service.best_effort([_record(weight=100.0, reps=5)])

    hits = history_service.detect_new_records(session_best, None)

    kinds = {hit.kind for hit in hits}
    assert kinds == {
        PersonalRecordKind.HEAVIEST_WEIGHT,
        PersonalRecordKind.BEST_ESTIMATED_ONE_RM,
    }


def test_detect_new_records_strictly_beating_the_prior_best_is_a_record():
    prior_best = history_service.best_effort([_record(weight=100.0, reps=5)])
    session_best = history_service.best_effort([_record(weight=102.5, reps=5)])

    hits = history_service.detect_new_records(session_best, prior_best)

    assert any(hit.kind == PersonalRecordKind.HEAVIEST_WEIGHT for hit in hits)


def test_detect_new_records_matching_the_prior_best_exactly_is_not_a_record():
    prior_best = history_service.best_effort([_record(weight=100.0, reps=5)])
    session_best = history_service.best_effort([_record(weight=100.0, reps=5)])

    hits = history_service.detect_new_records(session_best, prior_best)

    assert hits == []


def test_detect_new_records_falling_short_of_the_prior_best_is_not_a_record():
    prior_best = history_service.best_effort([_record(weight=100.0, reps=5)])
    session_best = history_service.best_effort([_record(weight=90.0, reps=5)])

    hits = history_service.detect_new_records(session_best, prior_best)

    assert hits == []


def test_detect_new_records_cross_unit_match_within_epsilon_is_not_a_record():
    # 100 kg logged once, then the exact same weight logged again in lb — a
    # round trip through the conversion factor should not manufacture a PR.
    prior_kg = _record(weight=100.0, reps=5, weight_unit=WeightUnit.KG)
    same_weight_in_lb = history_service.from_kg(100.0, WeightUnit.LB)
    session_lb = _record(weight=same_weight_in_lb, reps=5, weight_unit=WeightUnit.LB)
    prior_best = history_service.best_effort([prior_kg])
    session_best = history_service.best_effort([session_lb])

    hits = history_service.detect_new_records(session_best, prior_best)

    assert hits == []


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def _exercise(name: str = "Squat") -> MagicMock:
    exercise = MagicMock()
    exercise.name = name
    return exercise


def test_get_personal_records_for_unknown_exercise_raises_not_found(monkeypatch):
    monkeypatch.setattr(
        history_service.exercises_repo, "get_visible_exercise", lambda *a, **k: None
    )

    with pytest.raises(history_service.ExerciseNotFoundError):
        history_service.get_personal_records(
            MagicMock(),
            user_id=USER_ID,
            exercise_id=EXERCISE_ID,
            display_unit=WeightUnit.KG,
        )


def test_get_personal_records_with_no_logged_sets_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        history_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: _exercise(),
    )
    monkeypatch.setattr(
        history_service.history_repo,
        "list_weighted_performances_for_exercise",
        lambda *a, **k: [],
    )

    result = history_service.get_personal_records(
        MagicMock(),
        user_id=USER_ID,
        exercise_id=EXERCISE_ID,
        display_unit=WeightUnit.KG,
    )

    assert result == []


def test_get_personal_records_returns_both_kinds_converted_to_display_unit(
    monkeypatch,
):
    monkeypatch.setattr(
        history_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: _exercise("Bench Press"),
    )
    rows = [_row(weight=100.0, reps=5, unit=WeightUnit.KG)]
    monkeypatch.setattr(
        history_service.history_repo,
        "list_weighted_performances_for_exercise",
        lambda *a, **k: rows,
    )

    results = history_service.get_personal_records(
        MagicMock(),
        user_id=USER_ID,
        exercise_id=EXERCISE_ID,
        display_unit=WeightUnit.LB,
    )

    kinds = {record.kind for record in results}
    assert kinds == {
        PersonalRecordKind.HEAVIEST_WEIGHT,
        PersonalRecordKind.BEST_ESTIMATED_ONE_RM,
    }
    heaviest = next(r for r in results if r.kind == PersonalRecordKind.HEAVIEST_WEIGHT)
    assert heaviest.value == 100.0
    assert heaviest.recorded_unit == WeightUnit.KG
    assert heaviest.display_unit == WeightUnit.LB
    assert heaviest.converted is True
    assert heaviest.display_value == round(
        history_service.from_kg(100.0, WeightUnit.LB), 2
    )


def test_get_session_personal_records_for_incomplete_session_returns_empty_list(
    monkeypatch,
):
    workout_session = MagicMock(completed_at=None)
    monkeypatch.setattr(
        history_service.workout_sessions_service,
        "get_owned_workout_session",
        lambda *a, **k: workout_session,
    )

    result = history_service.get_session_personal_records(
        MagicMock(),
        user_id=USER_ID,
        workout_session_id=SESSION_ID,
        display_unit=WeightUnit.KG,
    )

    assert result == []


def test_get_session_personal_records_reports_only_beaten_records(monkeypatch):
    completed_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    workout_session = MagicMock(completed_at=completed_at, id=SESSION_ID)
    monkeypatch.setattr(
        history_service.workout_sessions_service,
        "get_owned_workout_session",
        lambda *a, **k: workout_session,
    )
    # Exercise name comes off the prescription's `exercise` relationship, not
    # a `get_visible_exercise` call — these exercises already belong to the
    # caller's own session, so no separate visibility lookup happens here.
    prescription = MagicMock(exercise_id=EXERCISE_ID, exercise=_exercise("Squat"))
    monkeypatch.setattr(
        history_service.exercise_prescriptions_repo,
        "list_exercise_prescriptions_for_session",
        lambda *a, **k: [prescription],
    )
    # A single heavy rep: beats the prior heaviest-weight (100 -> 105), but its
    # e1RM (105, unchanged for reps == 1) falls short of the prior e1RM
    # (100 * (1 + 8 / 30) ~= 126.7), so only the weight kind should be hit.
    prior_set = _row(
        weight=100.0,
        reps=8,
        performed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        workout_session_id=SESSION_ID - 1,
    )
    beating_set = _row(
        weight=105.0,
        reps=1,
        performed_at=completed_at,
        workout_session_id=SESSION_ID,
    )
    monkeypatch.setattr(
        history_service.history_repo,
        "list_weighted_performances_for_exercise",
        lambda *a, **k: [prior_set, beating_set],
    )

    results = history_service.get_session_personal_records(
        MagicMock(),
        user_id=USER_ID,
        workout_session_id=SESSION_ID,
        display_unit=WeightUnit.KG,
    )

    assert len(results) == 1
    assert results[0].kind == PersonalRecordKind.HEAVIEST_WEIGHT
    assert results[0].value == 105.0
    assert results[0].workout_session_id == SESSION_ID


def test_get_one_rm_trend_returns_one_point_per_session_newest_first(monkeypatch):
    monkeypatch.setattr(
        history_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: _exercise("Squat"),
    )
    older_session = _row(
        weight=100.0,
        reps=5,
        performed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        workout_session_id=1,
    )
    newer_session = _row(
        weight=105.0,
        reps=5,
        performed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        workout_session_id=2,
    )
    monkeypatch.setattr(
        history_service.history_repo,
        "list_weighted_performances_for_exercise",
        lambda *a, **k: [older_session, newer_session],
    )

    points = history_service.get_one_rm_trend(
        MagicMock(),
        user_id=USER_ID,
        exercise_id=EXERCISE_ID,
        program_id=None,
        limit=history_service.DEFAULT_LIST_LIMIT,
        offset=0,
        display_unit=WeightUnit.KG,
    )

    assert [point.workout_session_id for point in points] == [2, 1]


def test_get_one_rm_trend_filters_by_program_id(monkeypatch):
    monkeypatch.setattr(
        history_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: _exercise("Squat"),
    )
    get_owned_program_mock = MagicMock()
    monkeypatch.setattr(
        history_service.programs_service, "get_owned_program", get_owned_program_mock
    )
    other_program_session = _row(
        weight=100.0, reps=5, program_id=PROGRAM_ID + 1, workout_session_id=1
    )
    target_program_session = _row(
        weight=105.0, reps=5, program_id=PROGRAM_ID, workout_session_id=2
    )
    monkeypatch.setattr(
        history_service.history_repo,
        "list_weighted_performances_for_exercise",
        lambda *a, **k: [other_program_session, target_program_session],
    )

    points = history_service.get_one_rm_trend(
        MagicMock(),
        user_id=USER_ID,
        exercise_id=EXERCISE_ID,
        program_id=PROGRAM_ID,
        limit=history_service.DEFAULT_LIST_LIMIT,
        offset=0,
        display_unit=WeightUnit.KG,
    )

    get_owned_program_mock.assert_called_once()
    assert [point.program_id for point in points] == [PROGRAM_ID]


def test_get_one_rm_trend_applies_limit_and_offset(monkeypatch):
    monkeypatch.setattr(
        history_service.exercises_repo,
        "get_visible_exercise",
        lambda *a, **k: _exercise("Squat"),
    )
    rows = [
        _row(
            weight=100.0 + i,
            reps=5,
            performed_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            workout_session_id=i,
        )
        for i in range(5)
    ]
    monkeypatch.setattr(
        history_service.history_repo,
        "list_weighted_performances_for_exercise",
        lambda *a, **k: rows,
    )

    points = history_service.get_one_rm_trend(
        MagicMock(),
        user_id=USER_ID,
        exercise_id=EXERCISE_ID,
        program_id=None,
        limit=2,
        offset=1,
        display_unit=WeightUnit.KG,
    )

    # Newest first: sessions 4,3,2,1,0 -> offset 1, limit 2 -> [3, 2]
    assert [point.workout_session_id for point in points] == [3, 2]


def test_list_completed_sessions_checks_program_ownership_when_program_id_given(
    monkeypatch,
):
    get_owned_program_mock = MagicMock()
    monkeypatch.setattr(
        history_service.programs_service, "get_owned_program", get_owned_program_mock
    )
    monkeypatch.setattr(
        history_service.history_repo, "list_completed_sessions", lambda *a, **k: []
    )
    session = MagicMock()

    history_service.list_completed_sessions(
        session,
        user_id=USER_ID,
        program_id=PROGRAM_ID,
        limit=history_service.DEFAULT_LIST_LIMIT,
        offset=0,
    )

    get_owned_program_mock.assert_called_once_with(
        session, user_id=USER_ID, program_id=PROGRAM_ID
    )


def test_list_completed_sessions_without_program_id_skips_ownership_check(
    monkeypatch,
):
    get_owned_program_mock = MagicMock()
    monkeypatch.setattr(
        history_service.programs_service, "get_owned_program", get_owned_program_mock
    )
    monkeypatch.setattr(
        history_service.history_repo, "list_completed_sessions", lambda *a, **k: []
    )

    history_service.list_completed_sessions(
        MagicMock(),
        user_id=USER_ID,
        program_id=None,
        limit=history_service.DEFAULT_LIST_LIMIT,
        offset=0,
    )

    get_owned_program_mock.assert_not_called()

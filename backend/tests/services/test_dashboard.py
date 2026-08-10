"""Unit tests for app.services.dashboard.

`resolve_program_status` and `fold_exercise_history` are the pure core (no
Session, no I/O) and get the bulk of the coverage — per TRAIN-22's design plan
this is "the branchiest logic in the ticket". `get_dashboard` is orchestration
and is tested by mocking its repository collaborators.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.models.enums import PersonalRecordKind, WeightUnit
from app.services import dashboard as dashboard_service
from app.services.dashboard import ProgramSessionRow
from app.services.history import PerformanceRecord

USER_ID = 1
PROGRAM_ID = 3
EXERCISE_ID = 20
WINDOW_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _session_row(
    *,
    id: int,
    week_number: int = 1,
    order_index: int = 0,
    week_id: int = 1,
    day_name: str = "Day A",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    prescription_count: int = 1,
) -> ProgramSessionRow:
    return ProgramSessionRow(
        id=id,
        week_id=week_id,
        week_number=week_number,
        order_index=order_index,
        day_name=day_name,
        started_at=started_at,
        completed_at=completed_at,
        prescription_count=prescription_count,
    )


def _record(
    *,
    weight: float,
    reps: int,
    performed_at: datetime,
    workout_session_id: int,
    weight_unit: WeightUnit = WeightUnit.KG,
    program_id: int = PROGRAM_ID,
    progression_line_id: int = 7,
) -> PerformanceRecord:
    return PerformanceRecord(
        weight=weight,
        reps=reps,
        weight_unit=weight_unit,
        performed_at=performed_at,
        workout_session_id=workout_session_id,
        program_id=program_id,
        progression_line_id=progression_line_id,
    )


# --------------------------------------------------------------------------
# resolve_program_status
# --------------------------------------------------------------------------


def test_resolve_program_status_with_no_sessions_reports_incomplete_and_no_next():
    status = dashboard_service.resolve_program_status([])

    assert status.next_workout is None
    assert status.program_complete is False
    assert status.sessions_total == 0
    assert status.current_week_number is None


def test_resolve_program_status_with_nothing_completed_picks_first_in_order():
    first = _session_row(id=1, week_number=1, order_index=0)
    second = _session_row(id=2, week_number=1, order_index=1)

    status = dashboard_service.resolve_program_status([second, first])

    assert status.next_workout.id == first.id
    assert status.program_complete is False


def test_resolve_program_status_resumes_an_in_progress_session_over_continuing():
    completed = _session_row(
        id=1,
        week_number=1,
        order_index=0,
        completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    in_progress = _session_row(
        id=2, week_number=1, order_index=1, started_at=datetime.now(timezone.utc)
    )
    not_started = _session_row(id=3, week_number=1, order_index=2)

    status = dashboard_service.resolve_program_status(
        [completed, in_progress, not_started]
    )

    assert status.next_workout.id == in_progress.id
    assert status.program_complete is False


def test_resolve_program_status_with_multiple_in_progress_takes_the_earliest():
    earlier_in_progress = _session_row(
        id=1, week_number=1, order_index=0, started_at=datetime.now(timezone.utc)
    )
    later_in_progress = _session_row(
        id=2, week_number=1, order_index=1, started_at=datetime.now(timezone.utc)
    )

    status = dashboard_service.resolve_program_status(
        [later_in_progress, earlier_in_progress]
    )

    assert status.next_workout.id == earlier_in_progress.id


def test_resolve_program_status_continues_from_the_cursor_after_last_completed():
    completed = _session_row(
        id=1,
        week_number=1,
        order_index=0,
        completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    upcoming = _session_row(id=2, week_number=1, order_index=1)

    status = dashboard_service.resolve_program_status([completed, upcoming])

    assert status.next_workout.id == upcoming.id
    assert status.program_complete is False


def test_resolve_program_status_never_resurfaces_a_session_skipped_before_the_cursor():
    # Session 1 (week 1) was skipped entirely; the athlete completed session 2
    # (week 2) instead. Per "resume, then continue" (option B), session 1 must
    # never resurface as next_workout, even though it's still not completed.
    skipped = _session_row(id=1, week_number=1, order_index=0)
    completed = _session_row(
        id=2,
        week_number=2,
        order_index=0,
        completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    status = dashboard_service.resolve_program_status([skipped, completed])

    assert status.next_workout is None
    assert status.program_complete is True
    # The skip still shows up in program_progress, per the design plan.
    assert status.sessions_completed == 1
    assert status.sessions_total == 2


def test_resolve_program_status_uses_completed_at_desc_id_desc_for_the_cursor():
    # Two sessions completed at the exact same timestamp (a tiebreak edge
    # case) — the cursor must be the higher id, matching
    # `history_repo.list_completed_sessions`' convention.
    same_instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lower_id = _session_row(
        id=1, week_number=1, order_index=0, completed_at=same_instant
    )
    higher_id = _session_row(
        id=2, week_number=1, order_index=1, completed_at=same_instant
    )
    upcoming = _session_row(id=3, week_number=1, order_index=2)

    status = dashboard_service.resolve_program_status([upcoming, lower_id, higher_id])

    assert status.next_workout.id == upcoming.id


def test_resolve_program_status_reports_program_progress_and_current_week_counts():
    week1_completed = _session_row(
        id=1,
        week_number=1,
        order_index=0,
        completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    week2_completed = _session_row(
        id=2,
        week_number=2,
        order_index=0,
        completed_at=datetime(2026, 1, 8, tzinfo=timezone.utc),
    )
    week2_upcoming = _session_row(id=3, week_number=2, order_index=1)

    status = dashboard_service.resolve_program_status(
        [week1_completed, week2_completed, week2_upcoming]
    )

    assert status.sessions_completed == 2
    assert status.sessions_total == 3
    assert status.current_week_number == 2
    assert status.current_week_sessions_completed == 1
    assert status.current_week_sessions_total == 2


# --------------------------------------------------------------------------
# fold_exercise_history
# --------------------------------------------------------------------------


def test_fold_exercise_history_with_only_in_window_records_has_no_prior_best():
    record = _record(
        weight=100.0, reps=5, performed_at=WINDOW_START, workout_session_id=1
    )

    fold = dashboard_service.fold_exercise_history([record], window_start=WINDOW_START)

    assert len(fold.hits) == 2  # first-ever effort is a record on both kinds
    assert fold.best_before_window is None
    assert fold.best_in_window.best_weight.weight == record.weight


def test_fold_exercise_history_computes_delta_between_window_and_prior_bests():
    before_window = _record(
        weight=100.0,
        reps=5,
        performed_at=WINDOW_START - timedelta(days=1),
        workout_session_id=1,
    )
    in_window = _record(
        weight=105.0, reps=5, performed_at=WINDOW_START, workout_session_id=2
    )

    fold = dashboard_service.fold_exercise_history(
        [before_window, in_window], window_start=WINDOW_START
    )

    assert fold.best_before_window.best_weight.weight == before_window.weight
    assert fold.best_in_window.best_weight.weight == in_window.weight


def test_fold_exercise_history_only_reports_prs_actually_beaten_within_the_window():
    before_window = _record(
        weight=100.0,
        reps=5,
        performed_at=WINDOW_START - timedelta(days=1),
        workout_session_id=1,
    )
    tied_in_window = _record(
        weight=100.0, reps=5, performed_at=WINDOW_START, workout_session_id=2
    )

    fold = dashboard_service.fold_exercise_history(
        [before_window, tied_in_window], window_start=WINDOW_START
    )

    assert fold.hits == []


def test_fold_exercise_history_compares_each_in_window_session_against_the_true_prior_best():
    # Three sessions all within the window: the middle one sets a PR, the
    # last one is lower than the middle but still needs comparing against the
    # *running* best (the middle session), not the window's first session.
    first = _record(
        weight=100.0, reps=5, performed_at=WINDOW_START, workout_session_id=1
    )
    second = _record(
        weight=110.0,
        reps=5,
        performed_at=WINDOW_START + timedelta(days=1),
        workout_session_id=2,
    )
    third = _record(
        weight=105.0,
        reps=5,
        performed_at=WINDOW_START + timedelta(days=2),
        workout_session_id=3,
    )

    fold = dashboard_service.fold_exercise_history(
        [first, second, third], window_start=WINDOW_START
    )

    weight_hits = [
        hit for hit in fold.hits if hit.kind == PersonalRecordKind.HEAVIEST_WEIGHT
    ]
    beaten_session_ids = {hit.effort.workout_session_id for hit in weight_hits}
    assert beaten_session_ids == {first.workout_session_id, second.workout_session_id}


def test_merge_best_effort_ties_favor_the_earlier_running_effort():
    # _better_effort's docstring claims ties favor `running` (the earlier
    # occurrence, by construction of the fold's oldest-first walk) — pin that
    # invariant directly rather than relying on it only being implied by
    # fold_exercise_history's higher-level behavior.
    earlier = _record(
        weight=100.0, reps=5, performed_at=WINDOW_START, workout_session_id=1
    )
    later_tied = _record(
        weight=100.0,
        reps=5,
        performed_at=WINDOW_START + timedelta(days=1),
        workout_session_id=2,
    )
    running = dashboard_service.best_effort([earlier])
    session_best = dashboard_service.best_effort([later_tied])

    merged = dashboard_service._merge_best_effort(running, session_best)

    assert merged.best_weight.workout_session_id == earlier.workout_session_id
    assert merged.best_one_rm.workout_session_id == earlier.workout_session_id


def test_fold_exercise_history_boundary_timestamp_is_treated_as_in_window():
    on_boundary = _record(
        weight=100.0, reps=5, performed_at=WINDOW_START, workout_session_id=1
    )

    fold = dashboard_service.fold_exercise_history(
        [on_boundary], window_start=WINDOW_START
    )

    assert fold.best_in_window is not None
    assert fold.best_before_window is None


# --------------------------------------------------------------------------
# get_dashboard (orchestration)
# --------------------------------------------------------------------------


def test_get_dashboard_with_no_active_program_nulls_program_fields(monkeypatch):
    monkeypatch.setattr(
        dashboard_service.programs_repo, "get_active_program", lambda *a, **k: None
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo,
        "list_completed_at_since",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo, "get_last_completed_at", lambda *a, **k: None
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo, "list_recent_exercise_ids", lambda *a, **k: []
    )

    result = dashboard_service.get_dashboard(
        MagicMock(), user_id=USER_ID, display_unit=WeightUnit.KG
    )

    assert result.active_program is None
    assert result.program_progress is None
    assert result.next_workout is None
    assert result.program_complete is False
    assert result.recent_personal_records == []
    assert result.exercise_trends == []


def test_get_dashboard_with_active_program_populates_program_progress_and_next_workout(
    monkeypatch,
):
    program = MagicMock(
        id=PROGRAM_ID,
        weight_unit=WeightUnit.KG,
        start_date=None,
        end_date=None,
    )
    program.name = (
        "Texas Method"  # MagicMock(name=...) sets the repr, not the attribute
    )
    monkeypatch.setattr(
        dashboard_service.programs_repo, "get_active_program", lambda *a, **k: program
    )
    upcoming_session = MagicMock(
        id=11,
        week_id=5,
        order_index=0,
        day_name="Day A",
        started_at=None,
        completed_at=None,
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo,
        "list_program_sessions",
        lambda *a, **k: [(upcoming_session, 1, 3)],
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo,
        "list_completed_at_since",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo, "get_last_completed_at", lambda *a, **k: None
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo, "list_recent_exercise_ids", lambda *a, **k: []
    )

    result = dashboard_service.get_dashboard(
        MagicMock(), user_id=USER_ID, display_unit=WeightUnit.KG
    )

    assert result.active_program.id == PROGRAM_ID
    assert result.program_progress.program.sessions_total == 1
    assert result.next_workout.id == upcoming_session.id
    assert result.next_workout.status == "not_started"


def test_get_dashboard_rolling_window_counts_come_from_the_28_day_repo_call(
    monkeypatch,
):
    monkeypatch.setattr(
        dashboard_service.programs_repo, "get_active_program", lambda *a, **k: None
    )
    now = datetime.now(timezone.utc)
    within_seven_days = now - timedelta(days=1)
    within_twenty_eight_days = now - timedelta(days=20)
    last_completed_at = now - timedelta(days=5)
    monkeypatch.setattr(
        dashboard_service.dashboard_repo,
        "list_completed_at_since",
        lambda *a, **k: [within_seven_days, within_twenty_eight_days],
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo,
        "get_last_completed_at",
        lambda *a, **k: last_completed_at,
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo, "list_recent_exercise_ids", lambda *a, **k: []
    )

    result = dashboard_service.get_dashboard(
        MagicMock(), user_id=USER_ID, display_unit=WeightUnit.KG
    )

    assert result.consistency.sessions_completed_last_7_days == 1
    assert result.consistency.sessions_completed_last_28_days == 2
    assert result.consistency.days_since_last_session == 5


def test_get_dashboard_folds_recent_exercises_into_prs_and_trends(monkeypatch):
    monkeypatch.setattr(
        dashboard_service.programs_repo, "get_active_program", lambda *a, **k: None
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo,
        "list_completed_at_since",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo, "get_last_completed_at", lambda *a, **k: None
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo,
        "list_recent_exercise_ids",
        lambda *a, **k: [EXERCISE_ID],
    )
    now = datetime.now(timezone.utc)
    row = (
        EXERCISE_ID,
        "Squat",
        100.0,
        5,
        WeightUnit.KG,
        now,
        1,
        PROGRAM_ID,
        7,
    )
    monkeypatch.setattr(
        dashboard_service.history_repo,
        "list_weighted_performances_for_exercises",
        lambda *a, **k: [row],
    )

    result = dashboard_service.get_dashboard(
        MagicMock(), user_id=USER_ID, display_unit=WeightUnit.KG
    )

    assert len(result.recent_personal_records) == 2
    assert result.recent_personal_records[0].exercise_name == "Squat"
    assert len(result.exercise_trends) == 1
    assert result.exercise_trends[0].best_one_rm_before_window is None
    assert result.exercise_trends[0].delta is None


def test_get_dashboard_with_no_recent_exercises_skips_the_batched_history_query(
    monkeypatch,
):
    monkeypatch.setattr(
        dashboard_service.programs_repo, "get_active_program", lambda *a, **k: None
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo,
        "list_completed_at_since",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo, "get_last_completed_at", lambda *a, **k: None
    )
    monkeypatch.setattr(
        dashboard_service.dashboard_repo, "list_recent_exercise_ids", lambda *a, **k: []
    )
    batched_query = MagicMock()
    monkeypatch.setattr(
        dashboard_service.history_repo,
        "list_weighted_performances_for_exercises",
        batched_query,
    )

    dashboard_service.get_dashboard(
        MagicMock(), user_id=USER_ID, display_unit=WeightUnit.KG
    )

    batched_query.assert_not_called()

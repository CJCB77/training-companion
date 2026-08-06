"""Unit tests for the pure progression engine — `calculate_recommendation` and its
helpers in `app.services.progression`. No DB, no mocking of the engine itself, per
CLAUDE.md's testing philosophy: these exercise the real calculation logic directly.
"""

from app.models.enums import ProgressionType, SetCompletionState, WeightUnit
from app.schemas.progression import DeloadSettings, ProgressionSettings
from app.services.progression import (
    AttemptOutcome,
    build_attempt_history,
    calculate_recommendation,
    evaluate_attempt,
    resolve_settings,
)

CURRENT_WEIGHT = 100.0
TARGET_WEIGHT = 95.0
INCREMENT = 2.5
PERCENTAGE = 0.025
DELOAD_PERCENTAGE = 0.10
FAILURE_THRESHOLD = 3


def _settings(**overrides) -> ProgressionSettings:
    data = {
        "progression_type": ProgressionType.FIXED_INCREMENT,
        "increment": INCREMENT,
        "percentage": PERCENTAGE,
        "rounding_increment": 2.5,
        "deload": DeloadSettings(
            enabled=True,
            failure_threshold=FAILURE_THRESHOLD,
            percentage=DELOAD_PERCENTAGE,
        ),
    }
    data.update(overrides)
    return ProgressionSettings(**data)


def _success(weight: float = CURRENT_WEIGHT) -> AttemptOutcome:
    return AttemptOutcome(weight=weight, successful=True)


def _failure(weight: float = CURRENT_WEIGHT) -> AttemptOutcome:
    return AttemptOutcome(weight=weight, successful=False)


class TestNoData:
    def test_no_prior_attempts_returns_no_data_using_target_weight(self):
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[],
            settings=_settings(),
        )

        assert result.action == "no_data"
        assert result.recommended_weight == TARGET_WEIGHT
        assert result.current_weight == TARGET_WEIGHT
        assert result.consecutive_failures == 0


class TestSuccessStrategies:
    def test_fixed_increment_success_increases_by_increment(self):
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[_success()],
            settings=_settings(progression_type=ProgressionType.FIXED_INCREMENT),
        )

        assert result.action == "increase"
        assert result.recommended_weight == CURRENT_WEIGHT + INCREMENT
        assert result.current_weight == CURRENT_WEIGHT

    def test_percentage_success_increases_by_percentage(self):
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[_success()],
            settings=_settings(progression_type=ProgressionType.PERCENTAGE),
        )

        expected_raw = CURRENT_WEIGHT * (1 + PERCENTAGE)
        assert result.action == "increase"
        assert result.recommended_weight == round(expected_raw / 2.5) * 2.5

    def test_manual_success_holds_weight_with_manual_action(self):
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[_success()],
            settings=_settings(progression_type=ProgressionType.MANUAL),
        )

        assert result.action == "manual"
        assert result.recommended_weight == CURRENT_WEIGHT

    def test_fixed_increment_missing_increment_needs_configuration(self):
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[_success()],
            settings=_settings(
                progression_type=ProgressionType.FIXED_INCREMENT, increment=None
            ),
        )

        assert result.action == "needs_configuration"
        assert result.recommended_weight is None

    def test_percentage_missing_percentage_needs_configuration(self):
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[_success()],
            settings=_settings(
                progression_type=ProgressionType.PERCENTAGE, percentage=None
            ),
        )

        assert result.action == "needs_configuration"
        assert result.recommended_weight is None


class TestFailureHold:
    def test_single_failure_holds_same_weight(self):
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[_failure()],
            settings=_settings(),
        )

        assert result.action == "hold"
        assert result.recommended_weight == CURRENT_WEIGHT
        assert result.consecutive_failures == 1

    def test_failures_below_deload_threshold_still_hold(self):
        prior_attempts = [_failure()] * (FAILURE_THRESHOLD - 1)

        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=prior_attempts,
            settings=_settings(),
        )

        assert result.action == "hold"
        assert result.consecutive_failures == FAILURE_THRESHOLD - 1


class TestDeload:
    def test_failures_at_threshold_recommends_deload(self):
        prior_attempts = [_failure()] * FAILURE_THRESHOLD

        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=prior_attempts,
            settings=_settings(),
        )

        expected_raw = CURRENT_WEIGHT * (1 - DELOAD_PERCENTAGE)
        assert result.action == "deload"
        assert result.recommended_weight == round(expected_raw / 2.5) * 2.5
        assert result.consecutive_failures == FAILURE_THRESHOLD

    def test_failures_past_threshold_still_recommends_deload(self):
        prior_attempts = [_failure()] * (FAILURE_THRESHOLD + 2)

        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=prior_attempts,
            settings=_settings(),
        )

        assert result.action == "deload"

    def test_deload_disabled_holds_instead_of_deloading_past_threshold(self):
        prior_attempts = [_failure()] * (FAILURE_THRESHOLD + 2)

        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=prior_attempts,
            settings=_settings(
                deload=DeloadSettings(
                    enabled=False,
                    failure_threshold=FAILURE_THRESHOLD,
                    percentage=DELOAD_PERCENTAGE,
                )
            ),
        )

        assert result.action == "hold"

    def test_weight_decrease_resets_failure_count_and_avoids_re_deload(self):
        # Newest-first: two failures at the lower (post-deload) weight, then the
        # deload itself (a drop from 100 to 90), then more failures at 100 before
        # that. Without the weight-decrease reset this would total 5 failures and
        # re-trigger a deload immediately after one was just taken.
        deloaded_weight = CURRENT_WEIGHT * (1 - DELOAD_PERCENTAGE)
        prior_attempts = [
            _failure(weight=deloaded_weight),
            _failure(weight=deloaded_weight),
            _failure(weight=CURRENT_WEIGHT),
            _failure(weight=CURRENT_WEIGHT),
            _failure(weight=CURRENT_WEIGHT),
        ]

        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=prior_attempts,
            settings=_settings(),
        )

        assert result.consecutive_failures == 2
        assert result.action == "hold"

    def test_success_resets_failure_count_to_zero(self):
        # Newest-first: the most recent attempt succeeded, so failures from
        # further back must not be counted at all.
        prior_attempts = [_success(), _failure(), _failure()]

        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=prior_attempts,
            settings=_settings(progression_type=ProgressionType.FIXED_INCREMENT),
        )

        assert result.consecutive_failures == 0
        assert result.action == "increase"


class TestRounding:
    def test_rounds_to_kg_increment(self):
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[_success(weight=101.3)],
            settings=_settings(
                progression_type=ProgressionType.FIXED_INCREMENT,
                increment=2.5,
                rounding_increment=2.5,
            ),
        )

        assert result.recommended_weight == round((101.3 + 2.5) / 2.5) * 2.5

    def test_rounds_to_lb_increment(self):
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[_success(weight=203.0)],
            settings=_settings(
                progression_type=ProgressionType.FIXED_INCREMENT,
                increment=5.0,
                rounding_increment=5.0,
            ),
        )

        assert result.recommended_weight == round((203.0 + 5.0) / 5.0) * 5.0

    def test_current_weight_reported_unrounded(self):
        odd_weight = 101.3
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[_failure(weight=odd_weight)],
            settings=_settings(rounding_increment=2.5),
        )

        assert result.current_weight == odd_weight


class TestEvaluateAttempt:
    def _completed(self, actual_reps: int, weight: float = CURRENT_WEIGHT):
        return _FakePerformance(
            set_number=1,
            actual_reps=actual_reps,
            actual_weight=weight,
            completion_state=SetCompletionState.COMPLETED,
        )

    def test_all_sets_completed_at_or_above_target_reps_is_successful(self):
        performances = [self._completed(5), self._completed(6)]

        outcome = evaluate_attempt(
            target_sets=2, target_reps=5, performances=performances
        )

        assert outcome.successful is True
        assert outcome.weight == CURRENT_WEIGHT

    def test_fewer_sets_logged_than_target_is_a_failure(self):
        performances = [self._completed(5)]

        outcome = evaluate_attempt(
            target_sets=2, target_reps=5, performances=performances
        )

        assert outcome.successful is False

    def test_any_set_below_target_reps_is_a_failure(self):
        performances = [self._completed(5), self._completed(4)]

        outcome = evaluate_attempt(
            target_sets=2, target_reps=5, performances=performances
        )

        assert outcome.successful is False

    def test_skipped_set_is_a_failure(self):
        performances = [
            self._completed(5),
            _FakePerformance(
                set_number=2,
                actual_reps=5,
                actual_weight=CURRENT_WEIGHT,
                completion_state=SetCompletionState.SKIPPED,
            ),
        ]

        outcome = evaluate_attempt(
            target_sets=2, target_reps=5, performances=performances
        )

        assert outcome.successful is False

    def test_zero_logged_performances_evaluates_as_unsuccessful_in_isolation(self):
        # evaluate_attempt itself has no concept of "unattempted" — asked in
        # isolation whether zero sets satisfy "all target_sets sets logged", the
        # honest answer is no. The engine-level rule ("an unperformed session must
        # never push an athlete toward a deload") lives one layer up, in
        # build_attempt_history, which excludes empty-performance rows before they
        # ever reach this function — see TestBuildAttemptHistory below.
        outcome = evaluate_attempt(target_sets=2, target_reps=5, performances=[])

        assert outcome.successful is False
        assert outcome.weight is None


class _FakePerformance:
    """Minimal stand-in for `ExercisePerformance` — `evaluate_attempt` only reads
    these four attributes, so a full ORM instance (and DB) isn't needed.
    """

    def __init__(self, *, set_number, actual_reps, actual_weight, completion_state):
        self.set_number = set_number
        self.actual_reps = actual_reps
        self.actual_weight = actual_weight
        self.completion_state = completion_state


class _FakePrescription:
    """Minimal stand-in for `ExercisePrescription` — `build_attempt_history` only
    reads `target_sets`/`target_reps`, so a full ORM instance isn't needed.
    """

    def __init__(self, *, target_sets, target_reps):
        self.target_sets = target_sets
        self.target_reps = target_reps


class TestBuildAttemptHistory:
    """Covers the critical rule that a prescription with zero logged performances
    (a genuinely skipped exercise within an otherwise-completed session) must be
    excluded from history entirely — not scored as a failure.
    """

    def _completed(self, actual_reps: int = 5, weight: float = CURRENT_WEIGHT):
        return _FakePerformance(
            set_number=1,
            actual_reps=actual_reps,
            actual_weight=weight,
            completion_state=SetCompletionState.COMPLETED,
        )

    def test_row_with_zero_performances_is_excluded_not_counted_as_failure(self):
        skipped_row = (_FakePrescription(target_sets=2, target_reps=5), [])
        logged_row = (
            _FakePrescription(target_sets=1, target_reps=5),
            [self._completed()],
        )

        history = build_attempt_history([skipped_row, logged_row])

        assert len(history) == 1
        assert history[0].successful is True

    def test_all_rows_skipped_returns_empty_history(self):
        history = build_attempt_history(
            [
                (_FakePrescription(target_sets=2, target_reps=5), []),
                (_FakePrescription(target_sets=2, target_reps=5), []),
            ]
        )

        assert history == []

    def test_skipped_exercise_does_not_push_toward_deload(self):
        # A skipped attempt sandwiched in otherwise-failing history must not be
        # scored as an additional failure — only the two genuinely failed logged
        # attempts should count.
        failed = self._completed(actual_reps=1)  # below target_reps -> failure
        rows = [
            (_FakePrescription(target_sets=1, target_reps=5), [failed]),
            (_FakePrescription(target_sets=1, target_reps=5), []),  # skipped
            (_FakePrescription(target_sets=1, target_reps=5), [failed]),
        ]

        history = build_attempt_history(rows)
        settings = _settings(
            deload=DeloadSettings(
                enabled=True, failure_threshold=FAILURE_THRESHOLD, percentage=0.10
            )
        )
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT, prior_attempts=history, settings=settings
        )

        assert len(history) == 2
        assert result.consecutive_failures == 2
        assert result.action == "hold"


class _FakeSettingsContainer:
    """Minimal stand-ins for `resolve_settings`'s `prescription`/`program` args —
    only the attributes it reads are needed, no DB/factories required.
    """

    def __init__(self, **attrs):
        for key, value in attrs.items():
            setattr(self, key, value)


class TestResolveSettings:
    def test_prescription_param_overrides_program_default_per_key(self):
        prescription = _FakeSettingsContainer(
            progression_type=None,
            progression_params={"increment": 5.0},
        )
        program = _FakeSettingsContainer(
            default_progression_type=ProgressionType.FIXED_INCREMENT,
            default_progression_params={"increment": 2.5, "percentage": 0.03},
            weight_unit=WeightUnit.KG,
        )

        settings = resolve_settings(prescription=prescription, program=program)

        assert settings.increment == 5.0
        assert settings.percentage == 0.03

    def test_non_dict_progression_params_container_falls_back_without_raising(self):
        # The stored JSONB itself can be malformed at the container level, not
        # just at individual keys inside a dict — a legacy row could hold a list,
        # string, or number instead of an object entirely.
        prescription = _FakeSettingsContainer(
            progression_type=ProgressionType.FIXED_INCREMENT,
            progression_params=["not", "a", "dict"],
        )
        program = _FakeSettingsContainer(
            default_progression_type=None,
            default_progression_params="also not a dict",
            weight_unit=WeightUnit.KG,
        )

        settings = resolve_settings(prescription=prescription, program=program)

        assert settings.increment is None
        assert settings.percentage is None
        assert settings.deload.enabled is True
        assert settings.deload.failure_threshold == FAILURE_THRESHOLD
        assert settings.deload.percentage == DELOAD_PERCENTAGE
        assert settings.rounding_increment == 2.5

    def test_malformed_stored_config_falls_back_to_defaults_without_raising(self):
        prescription = _FakeSettingsContainer(
            progression_type=ProgressionType.FIXED_INCREMENT,
            progression_params={"increment": "not-a-number", "deload": "not-a-dict"},
        )
        program = _FakeSettingsContainer(
            default_progression_type=None,
            default_progression_params=None,
            weight_unit=WeightUnit.KG,
        )

        settings = resolve_settings(prescription=prescription, program=program)

        assert settings.increment is None
        assert settings.deload.enabled is True
        assert settings.deload.failure_threshold == FAILURE_THRESHOLD

    def test_unresolved_progression_type_defaults_to_manual(self):
        prescription = _FakeSettingsContainer(
            progression_type=None, progression_params=None
        )
        program = _FakeSettingsContainer(
            default_progression_type=None,
            default_progression_params=None,
            weight_unit=WeightUnit.KG,
        )

        settings = resolve_settings(prescription=prescription, program=program)

        assert settings.progression_type == ProgressionType.MANUAL

    def test_default_rounding_increment_is_2_5_for_kg_and_5_for_lb(self):
        prescription = _FakeSettingsContainer(
            progression_type=None, progression_params=None
        )

        kg_program = _FakeSettingsContainer(
            default_progression_type=None,
            default_progression_params=None,
            weight_unit=WeightUnit.KG,
        )
        lb_program = _FakeSettingsContainer(
            default_progression_type=None,
            default_progression_params=None,
            weight_unit=WeightUnit.LB,
        )

        kg_settings = resolve_settings(prescription=prescription, program=kg_program)
        lb_settings = resolve_settings(prescription=prescription, program=lb_program)

        assert kg_settings.rounding_increment == 2.5
        assert lb_settings.rounding_increment == 5.0

    def test_malformed_config_that_reaches_the_engine_returns_needs_configuration(
        self,
    ):
        # End-to-end tolerance check: a legacy row too malformed to supply an
        # increment must surface as `needs_configuration`, never a 500.
        prescription = _FakeSettingsContainer(
            progression_type=ProgressionType.FIXED_INCREMENT,
            progression_params={"increment": None},
        )
        program = _FakeSettingsContainer(
            default_progression_type=None,
            default_progression_params={"increment": []},
            weight_unit=WeightUnit.KG,
        )

        settings = resolve_settings(prescription=prescription, program=program)
        result = calculate_recommendation(
            target_weight=TARGET_WEIGHT,
            prior_attempts=[_success()],
            settings=settings,
        )

        assert result.action == "needs_configuration"

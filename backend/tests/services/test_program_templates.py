"""Tests for the program-templates seed data and app.services.program_templates.

Seed-integrity tests are pure Python (no DB) — they catch the whole class of JSONB/
name typos in `PROGRAM_TEMPLATE_SEED` in CI without ever touching Postgres.

The rest actually generates a program through `generate_program_from_template`
against a real `db_session` (marked `integration`): the load-bearing assertions here
are about what rows come out of `create_program_from_template_structure`'s
progression-line grouping algorithm, which only exists once ids are assigned by a
real flush/commit — a mocked repository can't stand in for that.
"""

import copy

import pytest
from sqlmodel import select

from app.data.seed_exercises import EXERCISE_SEED
from app.data.seed_program_templates import PROGRAM_TEMPLATE_SEED
from app.models.exercise import Exercise
from app.models.exercise_prescription import ExercisePrescription
from app.models.progression_line import ProgressionLine
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession
from app.schemas.program_templates import (
    ProgramGenerateRequest,
    TemplateStructure,
)
from app.services import program_templates as program_templates_service
from tests.factories import make_profile, make_program_template

KNOWN_EXERCISE_NAMES = {exercise["name"] for exercise in EXERCISE_SEED}


def _exercise_names_in(template: dict) -> set[str]:
    return {
        prescription["exercise_name"]
        for week in template["structure"]["weeks"]
        for session in week["sessions"]
        for prescription in session["prescriptions"]
    }


def _line_labels_by_group(template: dict) -> dict[tuple[str, str | None], set]:
    """Every distinct `line_label` seen for each `(exercise_name, line_key)` group
    within one template. A group is what `create_program_from_template_structure`
    collapses into a single `ProgressionLine` row (see `programs_repo`'s
    `line_specs` map) — if a group ever carried two different labels, generation
    would silently keep whichever label it saw first and discard the other. This
    is the invariant worth guarding in the seed data; "at most one default group
    per exercise" doesn't need its own test because a `line_key=None` grouping is
    definitionally a single group by dict-key construction, not something the seed
    could violate.
    """
    labels: dict[tuple[str, str | None], set] = {}
    for week in template["structure"]["weeks"]:
        for session in week["sessions"]:
            for prescription in session["prescriptions"]:
                key = (prescription["exercise_name"], prescription.get("line_key"))
                labels.setdefault(key, set()).add(prescription.get("line_label"))
    return labels


@pytest.mark.parametrize(
    "template", PROGRAM_TEMPLATE_SEED, ids=lambda template: template["slug"]
)
def test_seed_template_exercise_names_all_exist_in_exercise_seed(template):
    unresolvable = _exercise_names_in(template) - KNOWN_EXERCISE_NAMES

    assert unresolvable == set()


@pytest.mark.parametrize(
    "template", PROGRAM_TEMPLATE_SEED, ids=lambda template: template["slug"]
)
def test_seed_template_structure_validates_against_template_structure_schema(
    template,
):
    TemplateStructure.model_validate(template["structure"])


@pytest.mark.parametrize(
    "template", PROGRAM_TEMPLATE_SEED, ids=lambda template: template["slug"]
)
def test_seed_template_line_groups_never_carry_conflicting_labels(template):
    label_sets = _line_labels_by_group(template)

    assert all(len(labels) == 1 for labels in label_sets.values())


def test_seed_template_slugs_are_unique():
    slugs = [template["slug"] for template in PROGRAM_TEMPLATE_SEED]

    assert len(slugs) == len(set(slugs))


def test_generate_program_from_template_for_unknown_template_id_raises_not_found(
    monkeypatch,
):
    monkeypatch.setattr(
        program_templates_service.program_templates_repo,
        "get_program_template",
        lambda *a, **k: None,
    )

    with pytest.raises(program_templates_service.ProgramTemplateNotFoundError):
        program_templates_service.generate_program_from_template(
            None,
            user_id=1,
            template_id=999,
            payload=ProgramGenerateRequest(),
        )


def test_generate_program_from_template_raises_when_exercise_name_unresolvable(
    monkeypatch,
):
    """A template's structure referencing an exercise name absent from the system
    catalog is a seed-integrity bug, not bad client input — see
    `TemplateExerciseNotFoundError`'s docstring. Simulated here by monkeypatching
    the exercises-repo lookup to resolve nothing, rather than seeding a genuinely
    broken template — the seed itself is asserted clean by the seed-integrity
    tests above.
    """
    fake_template = make_program_template(**_stronglifts_seed())
    monkeypatch.setattr(
        program_templates_service.program_templates_repo,
        "get_program_template",
        lambda *a, **k: fake_template,
    )
    monkeypatch.setattr(
        program_templates_service.exercises_repo,
        "list_system_exercises_by_names",
        lambda *a, **k: [],
    )

    with pytest.raises(program_templates_service.TemplateExerciseNotFoundError):
        program_templates_service.generate_program_from_template(
            None,
            user_id=1,
            template_id=1,
            payload=ProgramGenerateRequest(),
        )


def _persist(session, *objs):
    for obj in objs:
        session.add(obj)
    session.flush()


def _seeded_template_data(slug: str) -> dict:
    """A copy of one real seed entry, with its `slug` replaced so persisting it in a
    test never collides with the real row the migration already seeded into the
    (shared, not per-test-database) `program_templates` table.
    """
    template = next(
        template for template in PROGRAM_TEMPLATE_SEED if template["slug"] == slug
    )
    # deepcopy, not a shallow dict spread: a shallow copy still shares the nested
    # weeks/sessions/prescriptions lists (and the `structure` dict itself) with the
    # module-level PROGRAM_TEMPLATE_SEED constant. Since `make_program_template`
    # hands `structure` straight to the ORM, any in-place mutation a test made to
    # its own copy would otherwise leak into every other test in the process.
    return {**copy.deepcopy(template), "slug": f"test-{slug}"}


def _stronglifts_seed() -> dict:
    return _seeded_template_data("stronglifts-5x5")


def _texas_method_seed() -> dict:
    return _seeded_template_data("texas-method")


def _generated_prescriptions(session, program_id: int) -> list[ExercisePrescription]:
    return list(
        session.exec(
            select(ExercisePrescription)
            .join(WorkoutSession)
            .join(TrainingWeek)
            .where(TrainingWeek.program_id == program_id)
        ).all()
    )


@pytest.mark.integration
def test_generate_stronglifts_squat_prescriptions_all_share_one_default_line(
    db_session,
):
    user = make_profile()
    template = make_program_template(**_stronglifts_seed())
    _persist(db_session, user, template)
    squat = db_session.exec(select(Exercise).where(Exercise.name == "Squat")).one()

    program = program_templates_service.generate_program_from_template(
        db_session,
        user_id=user.id,
        template_id=template.id,
        payload=ProgramGenerateRequest(),
    )

    prescriptions = _generated_prescriptions(db_session, program.id)
    squat_prescriptions = [rx for rx in prescriptions if rx.exercise_id == squat.id]
    # Every session in StrongLifts trains squat: A/B/A then B/A/B, six sessions total.
    assert len(squat_prescriptions) == 6
    # All of them resolve to the exact same ProgressionLine row: StrongLifts trains
    # squat every session with one intent, so this is the "zero setup" default-line
    # case — no split was ever declared in the seed.
    squat_line_ids = {rx.progression_line_id for rx in squat_prescriptions}
    assert len(squat_line_ids) == 1
    squat_line = db_session.get(ProgressionLine, next(iter(squat_line_ids)))
    assert squat_line.is_default is True


@pytest.mark.integration
def test_generate_texas_method_squat_resolves_to_three_distinct_lines(db_session):
    user = make_profile()
    template = make_program_template(**_texas_method_seed())
    _persist(db_session, user, template)

    program = program_templates_service.generate_program_from_template(
        db_session,
        user_id=user.id,
        template_id=template.id,
        payload=ProgramGenerateRequest(),
    )

    prescriptions_by_session_order = {
        (rx.workout_session_id, rx.order_index): rx
        for rx in _generated_prescriptions(db_session, program.id)
    }
    sessions_by_day = {
        session.day_name: session
        for session in db_session.exec(
            select(WorkoutSession)
            .join(TrainingWeek)
            .where(TrainingWeek.program_id == program.id)
        ).all()
    }
    volume_squat = prescriptions_by_session_order[(sessions_by_day["Volume Day"].id, 0)]
    light_squat = prescriptions_by_session_order[
        (sessions_by_day["Recovery Day"].id, 0)
    ]
    intensity_squat = prescriptions_by_session_order[
        (sessions_by_day["Intensity Day"].id, 0)
    ]

    line_ids = {
        volume_squat.progression_line_id,
        light_squat.progression_line_id,
        intensity_squat.progression_line_id,
    }
    assert len(line_ids) == 3

    lines = {line_id: db_session.get(ProgressionLine, line_id) for line_id in line_ids}
    default_lines = [line for line in lines.values() if line.is_default]
    labeled_lines = [line for line in lines.values() if not line.is_default]
    assert len(default_lines) == 1
    assert default_lines[0].id == intensity_squat.progression_line_id
    assert {line.label for line in labeled_lines} == {"Volume", "Light"}


@pytest.mark.integration
def test_generate_program_from_template_gives_every_prescription_a_null_target_weight(
    db_session,
):
    user = make_profile()
    template = make_program_template(**_stronglifts_seed())
    _persist(db_session, user, template)

    program = program_templates_service.generate_program_from_template(
        db_session,
        user_id=user.id,
        template_id=template.id,
        payload=ProgramGenerateRequest(),
    )

    prescriptions = _generated_prescriptions(db_session, program.id)
    assert prescriptions
    assert all(rx.target_weight is None for rx in prescriptions)


@pytest.mark.integration
def test_generate_program_from_template_starts_inactive_unarchived_and_unowned_dates(
    db_session,
):
    user = make_profile()
    template = make_program_template(**_stronglifts_seed())
    _persist(db_session, user, template)

    program = program_templates_service.generate_program_from_template(
        db_session,
        user_id=user.id,
        template_id=template.id,
        payload=ProgramGenerateRequest(),
    )

    assert program.user_id == user.id
    assert program.is_active is False
    assert program.archived_at is None
    assert program.start_date is None
    assert program.end_date is None

    sessions = db_session.exec(
        select(WorkoutSession)
        .join(TrainingWeek)
        .where(TrainingWeek.program_id == program.id)
    ).all()
    assert sessions
    for session_row in sessions:
        assert session_row.started_at is None
        assert session_row.completed_at is None
        assert session_row.notes is None


@pytest.mark.integration
def test_generate_program_from_template_leaves_the_template_row_unchanged(db_session):
    user = make_profile()
    template = make_program_template(**_stronglifts_seed())
    _persist(db_session, user, template)
    # deepcopy: a shallow dict() copy still shares the nested weeks/sessions lists
    # with `template.structure`, so an in-place mutation of those nested lists
    # would pass this assertion even though the template row was mutated.
    original_structure = copy.deepcopy(template.structure)

    program_templates_service.generate_program_from_template(
        db_session,
        user_id=user.id,
        template_id=template.id,
        payload=ProgramGenerateRequest(),
    )

    db_session.refresh(template)
    assert template.structure == original_structure
    assert template.name == "StrongLifts 5x5"


@pytest.mark.integration
def test_generate_program_from_template_twice_produces_two_independent_programs(
    db_session,
):
    user = make_profile()
    template = make_program_template(**_stronglifts_seed())
    _persist(db_session, user, template)

    first = program_templates_service.generate_program_from_template(
        db_session,
        user_id=user.id,
        template_id=template.id,
        payload=ProgramGenerateRequest(),
    )
    second = program_templates_service.generate_program_from_template(
        db_session,
        user_id=user.id,
        template_id=template.id,
        payload=ProgramGenerateRequest(),
    )

    assert first.id != second.id
    first_line_ids = {
        line.id
        for line in db_session.exec(
            select(ProgressionLine).where(ProgressionLine.program_id == first.id)
        ).all()
    }
    second_line_ids = {
        line.id
        for line in db_session.exec(
            select(ProgressionLine).where(ProgressionLine.program_id == second.id)
        ).all()
    }
    assert first_line_ids.isdisjoint(second_line_ids)

    first_week_ids = {
        week.id
        for week in db_session.exec(
            select(TrainingWeek).where(TrainingWeek.program_id == first.id)
        ).all()
    }
    second_week_ids = {
        week.id
        for week in db_session.exec(
            select(TrainingWeek).where(TrainingWeek.program_id == second.id)
        ).all()
    }
    assert first_week_ids.isdisjoint(second_week_ids)

    first_session_ids = {
        session_row.id
        for session_row in db_session.exec(
            select(WorkoutSession).where(WorkoutSession.week_id.in_(first_week_ids))
        ).all()
    }
    second_session_ids = {
        session_row.id
        for session_row in db_session.exec(
            select(WorkoutSession).where(WorkoutSession.week_id.in_(second_week_ids))
        ).all()
    }
    assert first_session_ids.isdisjoint(second_session_ids)

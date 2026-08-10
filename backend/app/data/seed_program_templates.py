"""Canonical list of system (built-in) program templates.

`PROGRAM_TEMPLATE_SEED` is the source of truth, mirroring `seed_exercises.py`'s
`EXERCISE_SEED` docstring-and-constant pattern: the seed Alembic migration snapshots
this list via `op.bulk_insert`, and app code/tests reference the same source rather
than duplicating it.

Each row's `structure` dict must validate against
`app.schemas.program_templates.TemplateStructure` — a pure-Python test asserts this
in CI, independent of any migration/DB. Every `exercise_name` referenced anywhere in
`structure` must also appear in `app.data.seed_exercises.EXERCISE_SEED`, since
generation resolves names against the system exercise catalog.

Progression-line grouping (see CLAUDE.md's "Progression Lines" and TRAIN-26): a
prescription with `line_key=None` belongs to that exercise's **default** line; a
non-null `line_key` starts (or joins) an explicit split line, decoratively labeled by
`line_label`. At most one `line_key=None` prescription-group per (template, exercise)
is enforced by the seed-integrity test, matching the DB's own
`ix_progression_lines_default_per_program_exercise` invariant.

`target_weight` is deliberately absent everywhere — see TRAIN-24's design plan
(resolved question 2): generated prescriptions always start with `target_weight=None`,
set by the user in their first session.
"""

from app.models.enums import ProgressionType, WeightUnit

PROGRAM_TEMPLATE_SEED: list[dict] = [
    {
        "slug": "stronglifts-5x5",
        "name": "StrongLifts 5x5",
        "description": (
            "Classic beginner linear-progression program: three full-body sessions "
            "a week, alternating Workout A and Workout B, five sets of five reps on "
            "every main lift."
        ),
        "weight_unit": WeightUnit.KG,
        "default_progression_type": ProgressionType.FIXED_INCREMENT,
        "default_progression_params": {"increment": 2.5, "rounding_increment": 2.5},
        "structure": {
            "weeks": [
                {
                    "week_number": 1,
                    "name": "Week 1",
                    "sessions": [
                        {
                            "day_name": "Workout A",
                            "order_index": 0,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Bench Press",
                                    "order_index": 1,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Barbell Row",
                                    "order_index": 2,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                            ],
                        },
                        {
                            "day_name": "Workout B",
                            "order_index": 1,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Overhead Press",
                                    "order_index": 1,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Deadlift",
                                    "order_index": 2,
                                    "target_sets": 1,
                                    "target_reps": 5,
                                    "progression_params": {"increment": 5.0},
                                },
                            ],
                        },
                        {
                            "day_name": "Workout A",
                            "order_index": 2,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Bench Press",
                                    "order_index": 1,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Barbell Row",
                                    "order_index": 2,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                            ],
                        },
                    ],
                },
                {
                    "week_number": 2,
                    "name": "Week 2",
                    "sessions": [
                        {
                            "day_name": "Workout B",
                            "order_index": 0,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Overhead Press",
                                    "order_index": 1,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Deadlift",
                                    "order_index": 2,
                                    "target_sets": 1,
                                    "target_reps": 5,
                                    "progression_params": {"increment": 5.0},
                                },
                            ],
                        },
                        {
                            "day_name": "Workout A",
                            "order_index": 1,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Bench Press",
                                    "order_index": 1,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Barbell Row",
                                    "order_index": 2,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                            ],
                        },
                        {
                            "day_name": "Workout B",
                            "order_index": 2,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Overhead Press",
                                    "order_index": 1,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Deadlift",
                                    "order_index": 2,
                                    "target_sets": 1,
                                    "target_reps": 5,
                                    "progression_params": {"increment": 5.0},
                                },
                            ],
                        },
                    ],
                },
            ]
        },
    },
    {
        "slug": "starting-strength",
        "name": "Starting Strength",
        "description": (
            "Beginner linear-progression program built around low-rep triples: two "
            "alternating full-body sessions a week, with a single top-set deadlift."
        ),
        "weight_unit": WeightUnit.KG,
        "default_progression_type": ProgressionType.FIXED_INCREMENT,
        "default_progression_params": {"increment": 2.5, "rounding_increment": 2.5},
        "structure": {
            "weeks": [
                {
                    "week_number": 1,
                    "name": "Week 1",
                    "sessions": [
                        {
                            "day_name": "Workout A",
                            "order_index": 0,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 3,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Overhead Press",
                                    "order_index": 1,
                                    "target_sets": 3,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Deadlift",
                                    "order_index": 2,
                                    "target_sets": 1,
                                    "target_reps": 5,
                                    "progression_params": {"increment": 5.0},
                                },
                            ],
                        },
                        {
                            "day_name": "Workout B",
                            "order_index": 1,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 3,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Bench Press",
                                    "order_index": 1,
                                    "target_sets": 3,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Chin-up",
                                    "order_index": 2,
                                    "target_sets": 3,
                                    "target_reps": 8,
                                },
                            ],
                        },
                    ],
                },
                {
                    "week_number": 2,
                    "name": "Week 2",
                    "sessions": [
                        {
                            "day_name": "Workout A",
                            "order_index": 0,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 3,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Overhead Press",
                                    "order_index": 1,
                                    "target_sets": 3,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Deadlift",
                                    "order_index": 2,
                                    "target_sets": 1,
                                    "target_reps": 5,
                                    "progression_params": {"increment": 5.0},
                                },
                            ],
                        },
                        {
                            "day_name": "Workout B",
                            "order_index": 1,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 3,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Bench Press",
                                    "order_index": 1,
                                    "target_sets": 3,
                                    "target_reps": 5,
                                },
                                {
                                    "exercise_name": "Chin-up",
                                    "order_index": 2,
                                    "target_sets": 3,
                                    "target_reps": 8,
                                },
                            ],
                        },
                    ],
                },
            ]
        },
    },
    {
        "slug": "texas-method",
        "name": "Texas Method",
        "description": (
            "Intermediate weekly-wave program: one high-volume day, one light "
            "recovery day, and one intensity day for the main lifts, repeating "
            "every week."
        ),
        "weight_unit": WeightUnit.KG,
        "default_progression_type": ProgressionType.FIXED_INCREMENT,
        "default_progression_params": {"increment": 2.5, "rounding_increment": 2.5},
        "structure": {
            "weeks": [
                {
                    "week_number": 1,
                    "name": "Week 1",
                    "sessions": [
                        {
                            "day_name": "Volume Day",
                            "order_index": 0,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                    "line_key": "volume",
                                    "line_label": "Volume",
                                },
                                {
                                    "exercise_name": "Bench Press",
                                    "order_index": 1,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                    "line_key": "volume",
                                    "line_label": "Volume",
                                },
                                {
                                    "exercise_name": "Barbell Row",
                                    "order_index": 2,
                                    "target_sets": 5,
                                    "target_reps": 5,
                                },
                            ],
                        },
                        {
                            "day_name": "Recovery Day",
                            "order_index": 1,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 2,
                                    "target_reps": 5,
                                    "target_rpe": 6.0,
                                    "line_key": "light",
                                    "line_label": "Light",
                                },
                                {
                                    "exercise_name": "Overhead Press",
                                    "order_index": 1,
                                    "target_sets": 3,
                                    "target_reps": 5,
                                    "line_key": "light",
                                    "line_label": "Light",
                                },
                                {
                                    "exercise_name": "Chin-up",
                                    "order_index": 2,
                                    "target_sets": 3,
                                    "target_reps": 8,
                                },
                            ],
                        },
                        {
                            "day_name": "Intensity Day",
                            "order_index": 2,
                            "prescriptions": [
                                {
                                    "exercise_name": "Squat",
                                    "order_index": 0,
                                    "target_sets": 1,
                                    "target_reps": 5,
                                    "target_rpe": 9.0,
                                },
                                {
                                    "exercise_name": "Bench Press",
                                    "order_index": 1,
                                    "target_sets": 1,
                                    "target_reps": 5,
                                    "target_rpe": 9.0,
                                },
                                {
                                    "exercise_name": "Overhead Press",
                                    "order_index": 2,
                                    "target_sets": 1,
                                    "target_reps": 5,
                                    "target_rpe": 9.0,
                                },
                                {
                                    "exercise_name": "Deadlift",
                                    "order_index": 3,
                                    "target_sets": 1,
                                    "target_reps": 5,
                                    "target_rpe": 9.0,
                                    "progression_params": {"increment": 5.0},
                                },
                            ],
                        },
                    ],
                }
            ]
        },
    },
]

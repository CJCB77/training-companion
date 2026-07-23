"""Canonical list of system (built-in) exercises.

`created_by_user_id` is implicitly NULL for every row — these belong to no user.
The seed Alembic migration snapshots this list via op.bulk_insert. Keeping the data
here (rather than only inside the migration) lets app code and tests reference the
same source. Enum values are stored as their string form to match the String columns.
"""

from app.models.enums import Equipment, ExerciseCategory, MuscleGroup

EXERCISE_SEED: list[dict] = [
    {
        "name": "Squat",
        "muscle_group": MuscleGroup.QUADS,
        "equipment": Equipment.BARBELL,
        "category": ExerciseCategory.COMPOUND,
        "description": "Barbell back squat.",
    },
    {
        "name": "Bench Press",
        "muscle_group": MuscleGroup.CHEST,
        "equipment": Equipment.BARBELL,
        "category": ExerciseCategory.COMPOUND,
        "description": "Flat barbell bench press.",
    },
    {
        "name": "Overhead Press",
        "muscle_group": MuscleGroup.SHOULDERS,
        "equipment": Equipment.BARBELL,
        "category": ExerciseCategory.COMPOUND,
        "description": "Standing barbell overhead press.",
    },
    {
        "name": "Deadlift",
        "muscle_group": MuscleGroup.BACK,
        "equipment": Equipment.BARBELL,
        "category": ExerciseCategory.COMPOUND,
        "description": "Conventional barbell deadlift.",
    },
    {
        "name": "Barbell Row",
        "muscle_group": MuscleGroup.BACK,
        "equipment": Equipment.BARBELL,
        "category": ExerciseCategory.COMPOUND,
        "description": "Bent-over barbell row.",
    },
    {
        "name": "Romanian Deadlift",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "equipment": Equipment.BARBELL,
        "category": ExerciseCategory.COMPOUND,
        "description": "Hip-hinge barbell Romanian deadlift.",
    },
    {
        "name": "Pull-up",
        "muscle_group": MuscleGroup.BACK,
        "equipment": Equipment.BODYWEIGHT,
        "category": ExerciseCategory.COMPOUND,
        "description": "Bodyweight pull-up, pronated grip.",
    },
    {
        "name": "Chin-up",
        "muscle_group": MuscleGroup.BACK,
        "equipment": Equipment.BODYWEIGHT,
        "category": ExerciseCategory.COMPOUND,
        "description": "Bodyweight chin-up, supinated grip.",
    },
    {
        "name": "Lat Pulldown",
        "muscle_group": MuscleGroup.BACK,
        "equipment": Equipment.CABLE,
        "category": ExerciseCategory.COMPOUND,
        "description": "Cable lat pulldown.",
    },
    {
        "name": "Leg Press",
        "muscle_group": MuscleGroup.QUADS,
        "equipment": Equipment.MACHINE,
        "category": ExerciseCategory.COMPOUND,
        "description": "Machine leg press.",
    },
    {
        "name": "Dumbbell Shoulder Press",
        "muscle_group": MuscleGroup.SHOULDERS,
        "equipment": Equipment.DUMBBELL,
        "category": ExerciseCategory.COMPOUND,
        "description": "Seated dumbbell shoulder press.",
    },
    {
        "name": "Dumbbell Curl",
        "muscle_group": MuscleGroup.BICEPS,
        "equipment": Equipment.DUMBBELL,
        "category": ExerciseCategory.ISOLATION,
        "description": "Standing dumbbell biceps curl.",
    },
    {
        "name": "Skull Crushers",
        "muscle_group": MuscleGroup.TRICEPS,
        "equipment": Equipment.BARBELL,
        "category": ExerciseCategory.ISOLATION,
        "description": "Lying triceps extension (EZ-bar or barbell).",
    },
    {
        "name": "Face Pull",
        "muscle_group": MuscleGroup.SHOULDERS,
        "equipment": Equipment.CABLE,
        "category": ExerciseCategory.ISOLATION,
        "description": "Cable face pull for rear delts.",
    },
    {
        "name": "Plank",
        "muscle_group": MuscleGroup.CORE,
        "equipment": Equipment.BODYWEIGHT,
        "category": ExerciseCategory.ISOLATION,
        "description": "Front plank hold.",
    },
]

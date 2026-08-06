from enum import StrEnum


class WeightUnit(StrEnum):
    KG = "kg"
    LB = "lb"


class ProgressionType(StrEnum):
    FIXED_INCREMENT = "fixed_increment"
    PERCENTAGE = "percentage"
    MANUAL = "manual"


class MuscleGroup(StrEnum):
    CHEST = "chest"
    BACK = "back"
    SHOULDERS = "shoulders"
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    CORE = "core"
    CALVES = "calves"
    FOREARMS = "forearms"
    FULL_BODY = "full_body"


class Equipment(StrEnum):
    BARBELL = "barbell"
    DUMBBELL = "dumbbell"
    MACHINE = "machine"
    CABLE = "cable"
    BODYWEIGHT = "bodyweight"
    KETTLEBELL = "kettlebell"
    BANDS = "bands"
    OTHER = "other"


class ExerciseCategory(StrEnum):
    COMPOUND = "compound"
    ISOLATION = "isolation"


class SetCompletionState(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

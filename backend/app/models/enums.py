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


class PersonalRecordKind(StrEnum):
    """The two lifetime-PR kinds tracked per exercise — see CLAUDE.md's "PR
    Detection" and TRAIN-21's design plan (Resolved question 1). Both are derived
    on demand from `ExercisePerformance`; neither is stored.
    """

    HEAVIEST_WEIGHT = "heaviest_weight"
    BEST_ESTIMATED_ONE_RM = "best_estimated_one_rm"

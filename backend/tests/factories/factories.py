"""Object builders for the training domain.

Pure builders — they construct (unpersisted) model instances. Tests add them to a
session and flush/commit. Per CLAUDE.md the domain is highly relational, so factories
keep test setup readable. A sequence counter keeps unique fields (names, emails)
collision-free within a test run.
"""

from itertools import count
from uuid import uuid4

from app.models.enums import (
    Equipment,
    ExerciseCategory,
    MuscleGroup,
    ProgressionType,
    SetCompletionState,
    WeightUnit,
)
from app.models.exercise import Exercise
from app.models.exercise_performance import ExercisePerformance
from app.models.exercise_prescription import ExercisePrescription
from app.models.profile import Profile
from app.models.program import Program
from app.models.program_template import ProgramTemplate
from app.models.progression_line import ProgressionLine
from app.models.training_week import TrainingWeek
from app.models.workout_session import WorkoutSession

_seq = count(1)


def make_profile(**overrides) -> Profile:
    n = next(_seq)
    data = {
        "supabase_user_id": uuid4(),
        "email": f"athlete{n}@example.com",
        "default_weight_unit": WeightUnit.KG,
    }
    data.update(overrides)
    return Profile(**data)


def make_exercise(**overrides) -> Exercise:
    n = next(_seq)
    data = {
        "name": f"Custom Exercise {n}",
        "muscle_group": MuscleGroup.CHEST,
        "equipment": Equipment.BARBELL,
        "category": ExerciseCategory.COMPOUND,
    }
    data.update(overrides)
    return Exercise(**data)


def make_program(*, user_id: int, **overrides) -> Program:
    n = next(_seq)
    data = {
        "user_id": user_id,
        "name": f"Program {n}",
        "weight_unit": WeightUnit.KG,
        "default_progression_type": ProgressionType.FIXED_INCREMENT,
        "default_progression_params": {"increment": 2.5},
    }
    data.update(overrides)
    return Program(**data)


def make_program_template(**overrides) -> ProgramTemplate:
    n = next(_seq)
    data = {
        "slug": f"template-{n}",
        "name": f"Template {n}",
        "description": None,
        "weight_unit": WeightUnit.KG,
        "default_progression_type": ProgressionType.FIXED_INCREMENT,
        "default_progression_params": {"increment": 2.5},
        "structure": {"weeks": []},
    }
    data.update(overrides)
    return ProgramTemplate(**data)


def make_training_week(*, program_id: int, **overrides) -> TrainingWeek:
    data = {
        "program_id": program_id,
        "week_number": 1,
        "name": "Week 1",
    }
    data.update(overrides)
    return TrainingWeek(**data)


def make_workout_session(*, week_id: int, **overrides) -> WorkoutSession:
    data = {
        "week_id": week_id,
        "day_name": "Day A",
        "order_index": 0,
    }
    data.update(overrides)
    return WorkoutSession(**data)


def make_progression_line(
    *, program_id: int, exercise_id: int, **overrides
) -> ProgressionLine:
    data = {
        "program_id": program_id,
        "exercise_id": exercise_id,
        "is_default": True,
        "label": None,
    }
    data.update(overrides)
    return ProgressionLine(**data)


def make_exercise_prescription(
    *, workout_session_id: int, exercise_id: int, progression_line_id: int, **overrides
) -> ExercisePrescription:
    data = {
        "workout_session_id": workout_session_id,
        "exercise_id": exercise_id,
        "progression_line_id": progression_line_id,
        "order_index": 0,
        "target_sets": 5,
        "target_reps": 5,
        "target_weight": 100.0,
        "target_rpe": 8.0,
    }
    data.update(overrides)
    return ExercisePrescription(**data)


def make_exercise_performance(
    *, prescription_id: int, **overrides
) -> ExercisePerformance:
    data = {
        "prescription_id": prescription_id,
        "set_number": 1,
        "actual_reps": 5,
        "actual_weight": 100.0,
        "actual_rpe": 8.0,
        "completion_state": SetCompletionState.COMPLETED,
    }
    data.update(overrides)
    return ExercisePerformance(**data)

# Import every SQLModel table module here so that it registers on
# SQLModel.metadata. Alembic's autogenerate (alembic/env.py) relies on this
# package importing all models.
from app.models.exercise import Exercise  # noqa: F401
from app.models.exercise_performance import ExercisePerformance  # noqa: F401
from app.models.exercise_prescription import ExercisePrescription  # noqa: F401
from app.models.profile import Profile  # noqa: F401
from app.models.program import Program  # noqa: F401
from app.models.training_week import TrainingWeek  # noqa: F401
from app.models.workout_session import WorkoutSession  # noqa: F401

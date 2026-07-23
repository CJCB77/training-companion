from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from app.models.enums import Equipment, ExerciseCategory, MuscleGroup
from app.models.timestamps import created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.exercise_prescription import ExercisePrescription


class Exercise(SQLModel, table=True):
    __tablename__ = "exercises"
    __table_args__ = (
        # System exercises (created_by_user_id IS NULL) must have unique names so
        # the seed is idempotent and we never show duplicates. Custom exercises are
        # not constrained — two users may both create "My Curl Variation".
        sa.Index(
            "uq_exercise_system_name",
            "name",
            unique=True,
            postgresql_where=sa.text("created_by_user_id IS NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None

    # NULL = system/seeded exercise available to everyone. Otherwise the owning user.
    created_by_user_id: int | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            index=True,
            nullable=True,
        ),
    )

    muscle_group: MuscleGroup = Field(sa_column=sa.Column(sa.String, nullable=False))
    equipment: Equipment = Field(sa_column=sa.Column(sa.String, nullable=False))
    category: ExerciseCategory | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )

    icon: str | None = None
    image_url: str | None = None
    video_url: str | None = None

    created_at: datetime | None = created_at_column()
    updated_at: datetime | None = updated_at_column()

    prescriptions: list["ExercisePrescription"] = Relationship(
        back_populates="exercise"
    )

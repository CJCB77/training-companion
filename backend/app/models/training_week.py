from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel

from app.models.timestamps import created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.program import Program
    from app.models.workout_session import WorkoutSession


class TrainingWeek(SQLModel, table=True):
    __tablename__ = "training_weeks"
    __table_args__ = (
        sa.UniqueConstraint(
            "program_id", "week_number", name="uq_training_week_program_number"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    program_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("programs.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    week_number: int
    name: str | None = None

    created_at: datetime | None = created_at_column()
    updated_at: datetime | None = updated_at_column()

    program: "Program" = Relationship(back_populates="training_weeks")
    workout_sessions: list["WorkoutSession"] = Relationship(
        back_populates="week",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

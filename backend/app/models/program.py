from datetime import date, datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

from app.models.enums import ProgressionType, WeightUnit
from app.models.timestamps import created_at_column, updated_at_column

if TYPE_CHECKING:
    from app.models.training_week import TrainingWeek


class Program(SQLModel, table=True):
    __tablename__ = "programs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(
        sa_column=sa.Column(
            sa.Integer,
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    name: str
    description: str | None = None

    # Timeframe. end_date is open-ended and can be pushed back when extending a cycle.
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool = False

    # Every weight in this program is stored as a raw number in this unit. A program
    # runs entirely in one unit, so progression math never converts -> no float drift.
    weight_unit: WeightUnit = Field(
        sa_column=sa.Column(sa.String, nullable=False, server_default=WeightUnit.KG)
    )

    # Program-wide default progression. Each ExercisePrescription may override it;
    # a NULL override there means "inherit these".
    default_progression_type: ProgressionType | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    default_progression_params: dict | None = Field(
        default=None, sa_column=sa.Column(JSONB, nullable=True)
    )

    # Soft delete: NULL means active. Set on DELETE /programs/{id} instead of removing
    # the row, so the full week -> session -> prescription tree (and training history
    # built on top of it) survives.
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True),
    )

    created_at: datetime | None = created_at_column()
    updated_at: datetime | None = updated_at_column()

    training_weeks: list["TrainingWeek"] = Relationship(
        back_populates="program",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class WorkoutSessionCreate(BaseModel):
    """`order_index` is optional — omitted, the service auto-assigns `max + 1`
    (or 0 for the week's first session). Week id comes from the path, never the
    body.
    """

    day_name: str
    order_index: int | None = Field(default=None, ge=0)


class WorkoutSessionUpdate(BaseModel):
    """All fields optional — only what's set is applied (partial update)."""

    day_name: str | None = None
    order_index: int | None = Field(default=None, ge=0)
    notes: str | None = None


class WorkoutSessionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    week_id: int
    day_name: str
    order_index: int
    started_at: datetime | None
    completed_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> Literal["not_started", "in_progress", "completed"]:
        """Derived from started_at/completed_at, never stored: not_started,
        in_progress, or completed.
        """
        if self.completed_at is not None:
            return "completed"
        if self.started_at is not None:
            return "in_progress"
        return "not_started"

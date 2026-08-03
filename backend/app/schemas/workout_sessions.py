from datetime import datetime

from pydantic import BaseModel, Field


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


class WorkoutSessionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    week_id: int
    day_name: str
    order_index: int
    created_at: datetime
    updated_at: datetime

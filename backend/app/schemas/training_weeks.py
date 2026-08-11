from datetime import datetime

from pydantic import BaseModel, Field


class TrainingWeekCreate(BaseModel):
    """`week_number` is optional — omitted, the service auto-assigns `max + 1`
    (or 1 for the program's first week). Program id comes from the path, never
    the body.
    """

    week_number: int | None = Field(default=None, ge=1)
    name: str | None = None


class TrainingWeekUpdate(BaseModel):
    """All fields optional — only what's set is applied (partial update)."""

    week_number: int | None = Field(default=None, ge=1)
    name: str | None = None


class TrainingWeekGenerateRequest(BaseModel):
    """Body for `POST /training-weeks/{week_id}/generate-next`. `name` defaults to
    NULL rather than copying the source week's name — carrying over "Week 1" would
    produce a second week with the same label.
    """

    name: str | None = None


class TrainingWeekRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    program_id: int
    week_number: int
    name: str | None
    created_at: datetime
    updated_at: datetime

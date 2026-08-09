from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _normalize_label(value: str | None) -> str | None:
    """Trim whitespace, empty string -> None. Shared by both schemas that accept a
    label so create and rename behave identically.
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ProgressionLineRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    program_id: int
    exercise_id: int
    is_default: bool
    label: str | None
    created_at: datetime
    updated_at: datetime


class ProgressionLineCreateRequest(BaseModel):
    """Nested inside `ExercisePrescriptionCreate.start_new_progression_line` — the
    "start a new line" branch of prescription creation. Not a standalone endpoint:
    creating the line inline with the prescription matches CLAUDE.md's "picking a
    line is the link, no separate confirmation step" and avoids orphan rows when a
    user abandons the picker.
    """

    label: str | None = Field(default=None, max_length=100)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        return _normalize_label(value)


class ProgressionLineUpdate(BaseModel):
    """Label-only update — `PATCH /progression-lines/{id}`. Never touches
    `is_default` or any prescription.
    """

    label: str | None = Field(default=None, max_length=100)

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str | None) -> str | None:
        return _normalize_label(value)

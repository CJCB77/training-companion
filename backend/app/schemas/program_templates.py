"""Schemas for `ProgramTemplate` — both the JSONB `structure` shape stored on the
model (validated at read/generate time, never trusted as raw dict) and the API
read/request schemas. See TRAIN-24's design plan.
"""

from pydantic import BaseModel

from app.models.enums import ProgressionType, WeightUnit
from app.schemas.progression import ProgressionParams


class TemplatePrescription(BaseModel):
    """One planned exercise slot within a template session.

    Deliberately **no `target_weight` field** — per TRAIN-24's resolved question 2,
    generated prescriptions always get a NULL weight; the schema simply cannot
    express something we've decided not to support. `line_key`/`line_label` encode
    the Progression Lines grouping (see CLAUDE.md's "Progression Lines"):
    `line_key=None` means this exercise's default line; a non-null `line_key` groups
    prescriptions that share it into one explicit split line, decoratively labeled
    by `line_label`.
    """

    model_config = {"extra": "forbid"}

    exercise_name: str
    order_index: int
    target_sets: int
    target_reps: int
    target_rpe: float | None = None
    line_key: str | None = None
    line_label: str | None = None
    progression_type: ProgressionType | None = None
    progression_params: ProgressionParams | None = None
    notes: str | None = None


class TemplateSession(BaseModel):
    model_config = {"extra": "forbid"}

    day_name: str
    order_index: int
    prescriptions: list[TemplatePrescription]


class TemplateWeek(BaseModel):
    model_config = {"extra": "forbid"}

    week_number: int
    name: str | None = None
    sessions: list[TemplateSession]


class TemplateStructure(BaseModel):
    """What `ProgramTemplate.structure`'s JSONB validates as."""

    model_config = {"extra": "forbid"}

    weeks: list[TemplateWeek]


class ProgramTemplateRead(BaseModel):
    """List view — no `structure` (a client browsing templates doesn't need the
    full tree; `ProgramTemplateDetail` is the preview-before-generating companion).
    """

    model_config = {"from_attributes": True}

    id: int
    slug: str
    name: str
    description: str | None
    weight_unit: WeightUnit
    default_progression_type: ProgressionType | None
    default_progression_params: dict | None


class ProgramTemplateDetail(ProgramTemplateRead):
    structure: TemplateStructure


class ProgramGenerateRequest(BaseModel):
    """Body for POST /program-templates/{id}/generate. Everything else about the
    generated copy is decided by the service/repository, matching TRAIN-23's
    duplicate-program precedent (`ProgramDuplicateRequest`).
    """

    name: str | None = None

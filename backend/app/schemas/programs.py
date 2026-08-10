from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import ProgressionType, WeightUnit
from app.schemas.progression import ProgressionParams


class ProgramCreate(BaseModel):
    name: str
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool = False
    weight_unit: WeightUnit = WeightUnit.KG
    default_progression_type: ProgressionType | None = None
    default_progression_params: ProgressionParams | None = None


class ProgramUpdate(BaseModel):
    """All fields optional — only what's set is applied (partial update)."""

    name: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None
    weight_unit: WeightUnit | None = None
    default_progression_type: ProgressionType | None = None
    default_progression_params: ProgressionParams | None = None


class ProgramDuplicateRequest(BaseModel):
    """Body for POST /programs/{id}/duplicate. Everything else about the copy is
    decided by the service/repository — see the duplication design notes on
    TRAIN-23 for why start_date/end_date and session execution state are cleared.
    """

    name: str | None = None


class ProgramRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    name: str
    description: str | None
    start_date: date | None
    end_date: date | None
    is_active: bool
    weight_unit: WeightUnit
    default_progression_type: ProgressionType | None
    default_progression_params: dict | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

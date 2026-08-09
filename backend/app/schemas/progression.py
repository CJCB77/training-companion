"""Progression config shapes and the recommendation response.

`ProgressionParams`/`DeloadParams` are the **strict** write-side models used by the
program and prescription write schemas (`extra="forbid"`, typed/ranged) — see
`app/schemas/programs.py` and `app/schemas/exercise_prescriptions.py`.

`ProgressionSettings` is the **tolerant** read-side resolved settings object the engine
(`app/services/progression.py`) works with. It is never built directly from raw JSONB —
`resolve_settings` extracts each key defensively first, so a malformed stored row can never
raise here. See "Validation boundary" in TRAIN-20's design plan for why write-time
validation and read-time tolerance both exist rather than just one.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import ProgressionType


class DeloadParams(BaseModel):
    """Deload sub-block of `progression_params`. Every field optional — a partial
    override (e.g. just `{"percentage": 0.15}`) is valid at the prescription level.
    """

    model_config = {"extra": "forbid"}

    enabled: bool | None = None
    failure_threshold: int | None = Field(default=None, ge=1)
    percentage: float | None = Field(default=None, gt=0, lt=1)


class ProgressionParams(BaseModel):
    """Write-side shape of `Program.default_progression_params` /
    `ExercisePrescription.progression_params`. Validates types/ranges of whatever keys
    are present; does not require strategy-specific keys (increment/percentage) to be
    present, since a prescription may legitimately only override the deload block.
    """

    model_config = {"extra": "forbid"}

    increment: float | None = Field(default=None, ge=0)
    percentage: float | None = Field(default=None, gt=0, lt=1)
    rounding_increment: float | None = Field(default=None, gt=0)
    deload: DeloadParams | None = None


class DeloadSettings(BaseModel):
    """Resolved (fully-populated) deload settings."""

    enabled: bool
    failure_threshold: int
    percentage: float


class ProgressionSettings(BaseModel):
    """Fully-resolved, per-key-merged settings for one recommendation calculation.
    Built by `resolve_settings` — never parsed directly from raw JSONB.
    """

    progression_type: ProgressionType
    increment: float | None
    percentage: float | None
    rounding_increment: float
    deload: DeloadSettings


class RecommendationRead(BaseModel):
    recommended_weight: float | None
    current_weight: float | None
    action: Literal[
        "increase", "hold", "deload", "manual", "no_data", "needs_configuration"
    ]
    progression_type: ProgressionType
    consecutive_failures: int
    reason: str
    settings_used: ProgressionSettings

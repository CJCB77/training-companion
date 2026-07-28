from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import Equipment, ExerciseCategory, MuscleGroup


class ExerciseCreate(BaseModel):
    """Payload for creating a custom exercise.

    No `created_by_user_id` field — ownership comes from the JWT, never the payload,
    so it can't be spoofed.
    """

    name: str = Field(min_length=1, max_length=100)
    muscle_group: MuscleGroup
    equipment: Equipment
    description: str | None = None
    category: ExerciseCategory | None = None
    icon: str | None = None
    image_url: str | None = None
    video_url: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class ExerciseRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    description: str | None
    muscle_group: MuscleGroup
    equipment: Equipment
    category: ExerciseCategory | None
    icon: str | None
    image_url: str | None
    video_url: str | None
    created_at: datetime
    updated_at: datetime
    is_custom: bool

    @model_validator(mode="before")
    @classmethod
    def _compute_is_custom(cls, data: Any) -> Any:
        """Derive `is_custom` from `created_by_user_id` on the ORM object.

        `Exercise` has no `is_custom` attribute — it's a view concern, not a stored
        column — so this fills it in before pydantic validates from attributes.
        """
        if isinstance(data, dict):
            return data
        created_by_user_id = getattr(data, "created_by_user_id", None)
        return {
            "id": data.id,
            "name": data.name,
            "description": data.description,
            "muscle_group": data.muscle_group,
            "equipment": data.equipment,
            "category": data.category,
            "icon": data.icon,
            "image_url": data.image_url,
            "video_url": data.video_url,
            "created_at": data.created_at,
            "updated_at": data.updated_at,
            "is_custom": created_by_user_id is not None,
        }

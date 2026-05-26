from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProfileRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    supabase_user_id: UUID
    email: str
    name: str | None
    created_at: datetime
    updated_at: datetime

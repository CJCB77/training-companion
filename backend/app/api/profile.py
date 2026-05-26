from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.models.profile import Profile
from app.schemas.profiles import ProfileRead

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileRead)
def get_profile(current_user: Profile = Depends(get_current_user)) -> Profile:
    return current_user

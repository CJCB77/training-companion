from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.profile import Profile
from app.schemas.dashboard import DashboardRead
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardRead)
def get_dashboard(
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> DashboardRead:
    """Everything scoped by `current_user.id` — no path parameter to forge,
    so there is no 404-vs-403 question here the way there is for programs/
    sessions/prescriptions.
    """
    return dashboard_service.get_dashboard(
        db_session,
        user_id=current_user.id,
        display_unit=current_user.default_weight_unit,
    )

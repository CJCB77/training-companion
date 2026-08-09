from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.models.profile import Profile
from app.schemas.progression import RecommendationRead
from app.services import progression as progression_service

router = APIRouter(tags=["progression"])


def _prescription_not_found() -> HTTPException:
    # Access-denied maps here too, deliberately: a non-owner shouldn't be able to
    # distinguish "not yours" from "doesn't exist".
    return HTTPException(status.HTTP_404_NOT_FOUND, "Exercise prescription not found")


@router.get(
    "/progression/exercise-prescriptions/{prescription_id}/recommendation",
    response_model=RecommendationRead,
)
def get_recommendation(
    prescription_id: int,
    current_user: Profile = Depends(get_current_user),
    db_session: Session = Depends(get_session),
) -> RecommendationRead:
    try:
        return progression_service.get_recommendation_for_prescription(
            db_session, user_id=current_user.id, prescription_id=prescription_id
        )
    except (
        progression_service.ExercisePrescriptionNotFoundError,
        progression_service.ExercisePrescriptionAccessDeniedError,
    ) as exc:
        raise _prescription_not_found() from exc

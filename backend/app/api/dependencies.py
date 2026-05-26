from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.database import get_session
from app.integrations.supabase_auth import validate_token
from app.models.profile import Profile
from app.repositories import profiles as profiles_repo

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    session: Session = Depends(get_session),
) -> Profile:
    claims = validate_token(credentials.credentials)
    return profiles_repo.get_or_create_profile(
        session=session,
        supabase_user_id=UUID(claims["sub"]),
        email=claims["email"],
    )

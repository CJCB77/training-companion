from uuid import UUID

from sqlmodel import Session, select

from app.models.profile import Profile


def get_by_supabase_user_id(session: Session, supabase_user_id: UUID) -> Profile | None:
    return session.exec(select(Profile).where(Profile.supabase_user_id == supabase_user_id)).first()


def create_profile(session: Session, supabase_user_id: UUID, email: str) -> Profile:
    profile = Profile(supabase_user_id=supabase_user_id, email=email)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def get_or_create_profile(session: Session, supabase_user_id: UUID, email: str) -> Profile:
    profile = get_by_supabase_user_id(session, supabase_user_id)
    if profile is None:
        profile = create_profile(session, supabase_user_id, email)
    return profile

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.core.config import settings


@lru_cache
def get_engine() -> Engine:
    # Lazily created so importing the app never requires a configured DATABASE_URL.
    # pool_pre_ping guards against connections dropped by the Supabase pooler.
    return create_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
    )


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session

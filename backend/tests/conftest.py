from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.database import get_engine
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """A Session bound to a single connection inside an outer transaction.

    Repository functions call session.commit() internally; join_transaction_mode=
    "create_savepoint" turns those into savepoint releases so the outer transaction
    can roll everything back at teardown — every test starts from the same DB state.
    Requires a reachable Postgres (DATABASE_URL); tests using it are marked
    `integration` and skipped by the default CI run.
    """
    engine = get_engine()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

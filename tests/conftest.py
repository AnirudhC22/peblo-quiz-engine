"""
pytest configuration — sets up an isolated in-memory SQLite database
for every test session so tests never touch the real peblo_quiz.db.
"""

import os
import pytest

# Point to in-memory SQLite before any app module is imported
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LLM_PROVIDER"] = "gemini"
os.environ["GEMINI_API_KEY"] = "test-key-not-used"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database_models import Base
from app.database.db import get_db
from app.main import app


# ---------------------------------------------------------------------------
# In-memory engine shared across the test session
# ---------------------------------------------------------------------------

TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Apply override before any test runs
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all tables once for the entire test session."""
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture(scope="session")
def client():
    """Shared TestClient for all tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    """Per-test DB session, rolls back after each test."""
    connection = TEST_ENGINE.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

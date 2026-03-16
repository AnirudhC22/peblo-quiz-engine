"""
Database setup — SQLAlchemy with SQLite (swappable to PostgreSQL via env var)
"""

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database_models import Base

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./peblo_quiz.db")

# SQLite-specific connect_args (not needed for PostgreSQL)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables on startup."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified.")


def get_db():
    """FastAPI dependency — yields a DB session and closes it after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

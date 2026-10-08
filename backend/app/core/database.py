"""SQLAlchemy database engine and session factory for SQLite."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def create_all_tables() -> None:
    """Create all tables defined by ORM models."""
    # Import models so their metadata is registered before create_all
    import app.models.equipment  # noqa: F401
    import app.models.request  # noqa: F401
    Base.metadata.create_all(bind=engine)

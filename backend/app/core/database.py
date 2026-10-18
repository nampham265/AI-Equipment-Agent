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
    try:
        with engine.connect() as conn:
            existing_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(equipment_requests)")}
            if existing_cols:
                for col_name, col_type in [
                    ("return_condition", "TEXT"),
                    ("return_condition_note", "TEXT"),
                    ("returned_at", "TEXT"),
                    ("rejection_reason", "TEXT"),
                ]:
                    if col_name not in existing_cols:
                        conn.exec_driver_sql(f"ALTER TABLE equipment_requests ADD COLUMN {col_name} {col_type}")
            conn.commit()
    except Exception:
        pass

"""Shared pytest fixtures (minimal - most tests use their own fixtures)."""
from __future__ import annotations

import os
os.environ.setdefault("AGENT_ROUTING_MODE", "legacy_only")

from app.core.config import settings
settings.AGENT_ROUTING_MODE = os.environ.get("AGENT_ROUTING_MODE", "legacy_only")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.database import Base
from app.core.deps import get_db

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_session() -> Session:
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    import app.models.equipment  # noqa
    import app.models.request  # noqa
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

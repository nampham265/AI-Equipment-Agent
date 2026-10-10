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


ORIGINAL_EXCEL_PATH = settings.resolved_excel_path


@pytest.fixture(autouse=True)
def isolate_excel_data(tmp_path, monkeypatch):
    """Ensure tests run against an isolated temporary copy of equipment_agent.xlsx."""
    import shutil
    if ORIGINAL_EXCEL_PATH.exists():
        tmp_file = tmp_path / "equipment_agent_test.xlsx"
        shutil.copyfile(ORIGINAL_EXCEL_PATH, tmp_file)
        monkeypatch.setattr(settings, "EXCEL_DATA_PATH", str(tmp_file.resolve()))



@pytest.fixture(autouse=True)
def clean_app_dependency_overrides():
    """Ensure app.dependency_overrides is clean and routing mode is reset before and after every test."""
    from app.main import app
    app.dependency_overrides.clear()
    settings.AGENT_ROUTING_MODE = "legacy_only"
    yield
    app.dependency_overrides.clear()
    settings.AGENT_ROUTING_MODE = "legacy_only"

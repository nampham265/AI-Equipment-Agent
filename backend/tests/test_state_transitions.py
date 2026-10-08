"""Tests for state machine transitions."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.request import RequestModel
from app.repositories.sqlite_request import SQLiteRequestRepository
from app.services.approval_service import ApprovalService, VALID_TRANSITIONS
from app.services.notification_service import NotificationService
from app.notifications.base import NotificationProvider


TEST_DB_URL = "sqlite:///:memory:"


class _NullNotificationProvider(NotificationProvider):
    """Notification provider that does nothing (for tests)."""
    def send_approval_notification(self, request, approved):
        pass


@pytest.fixture
def db():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    import app.models.equipment  # noqa
    import app.models.request  # noqa
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _make_request(db, status: str = "Pending") -> RequestModel:
    now = datetime.now(timezone.utc).isoformat()
    r = RequestModel(
        requester_name="Test User",
        requester_email="test@example.com",
        project="Test Project",
        equipment_id="EQ-001",
        quantity=1,
        needed_from="2025-01-01",
        needed_to="2025-01-10",
        purpose="Testing",
        priority_level="Medium",
        priority_reason="Test",
        status=status,
        created_at=now,
        modified_at=now,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _svc(db) -> ApprovalService:
    return ApprovalService(
        SQLiteRequestRepository(db),
        NotificationService(_NullNotificationProvider()),
    )


class TestValidTransitions:
    def test_pending_to_approved(self, db):
        r = _make_request(db, "Pending")
        result = _svc(db).approve(r.id)
        assert result.status == "Approved"

    def test_pending_to_rejected(self, db):
        r = _make_request(db, "Pending")
        result = _svc(db).reject(r.id)
        assert result.status == "Rejected"

    def test_pending_to_cancelled(self, db):
        r = _make_request(db, "Pending")
        result = _svc(db).cancel(r.id, requester_email="test@example.com")
        assert result.status == "Cancelled"

    def test_approved_to_borrowed(self, db):
        r = _make_request(db, "Approved")
        result = _svc(db).mark_borrowed(r.id)
        assert result.status == "Borrowed"

    def test_approved_to_cancelled(self, db):
        r = _make_request(db, "Approved")
        result = _svc(db).cancel(r.id, requester_email="test@example.com")
        assert result.status == "Cancelled"

    def test_borrowed_to_returned(self, db):
        r = _make_request(db, "Borrowed")
        result = _svc(db).mark_returned(r.id)
        assert result.status == "Returned"


class TestInvalidTransitions:
    def test_approved_to_rejected_fails(self, db):
        r = _make_request(db, "Approved")
        with pytest.raises(HTTPException) as exc_info:
            _svc(db).reject(r.id)
        assert exc_info.value.status_code == 409

    def test_borrowed_to_approved_fails(self, db):
        r = _make_request(db, "Borrowed")
        with pytest.raises(HTTPException) as exc_info:
            _svc(db).approve(r.id)
        assert exc_info.value.status_code == 409

    def test_rejected_to_approved_fails(self, db):
        r = _make_request(db, "Rejected")
        with pytest.raises(HTTPException) as exc_info:
            _svc(db).approve(r.id)
        assert exc_info.value.status_code == 409

    def test_returned_to_borrowed_fails(self, db):
        r = _make_request(db, "Returned")
        with pytest.raises(HTTPException) as exc_info:
            _svc(db).mark_borrowed(r.id)
        assert exc_info.value.status_code == 409

    def test_cancelled_to_approved_fails(self, db):
        r = _make_request(db, "Cancelled")
        with pytest.raises(HTTPException) as exc_info:
            _svc(db).approve(r.id)
        assert exc_info.value.status_code == 409

    def test_pending_to_returned_fails(self, db):
        r = _make_request(db, "Pending")
        with pytest.raises(HTTPException) as exc_info:
            _svc(db).mark_returned(r.id)
        assert exc_info.value.status_code == 409

    def test_cancel_wrong_user_fails(self, db):
        r = _make_request(db, "Pending")
        with pytest.raises(HTTPException) as exc_info:
            _svc(db).cancel(r.id, requester_email="other@example.com")
        assert exc_info.value.status_code == 403


class TestValidTransitionsMap:
    """Verify VALID_TRANSITIONS covers all required paths from spec."""

    def test_pending_targets(self):
        targets = VALID_TRANSITIONS["Pending"]
        assert "Approved" in targets
        assert "Rejected" in targets
        assert "Cancelled" in targets

    def test_approved_targets(self):
        targets = VALID_TRANSITIONS["Approved"]
        assert "Borrowed" in targets
        assert "Cancelled" in targets

    def test_borrowed_targets(self):
        assert VALID_TRANSITIONS["Borrowed"] == {"Returned"}

    def test_terminal_states_have_no_targets(self):
        for state in ("Rejected", "Returned", "Cancelled"):
            assert VALID_TRANSITIONS[state] == set()

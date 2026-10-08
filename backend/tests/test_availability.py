"""Tests for availability calculation logic."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.equipment import EquipmentModel
from app.models.request import RequestModel
from app.repositories.sqlite_equipment import SQLiteEquipmentRepository
from app.repositories.sqlite_request import SQLiteRequestRepository
from app.services.availability_service import AvailabilityService


TEST_DB_URL = "sqlite:///:memory:"


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


def _make_request(
    db,
    equipment_id: str = "EQ-001",
    quantity: int = 1,
    needed_from: str = "2025-01-01",
    needed_to: str = "2025-01-10",
    status: str = "Approved",
) -> RequestModel:
    now = datetime.now(timezone.utc).isoformat()
    r = RequestModel(
        requester_name="Test User",
        requester_email="test@example.com",
        project="Test Project",
        equipment_id=equipment_id,
        quantity=quantity,
        needed_from=needed_from,
        needed_to=needed_to,
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


class TestAvailabilityCalculation:
    def test_no_overlapping_requests(self, db):
        repo = SQLiteRequestRepository(db)
        svc = AvailabilityService(repo)

        result = svc.calculate(
            equipment_id="EQ-001",
            needed_from="2025-02-01",
            needed_to="2025-02-10",
            quantity_total=5,
        )

        assert result.committed_quantity == 0
        assert result.available_quantity == 5
        assert result.competing_pending_requests == []

    def test_fully_committed(self, db):
        _make_request(db, quantity=3, status="Approved",
                      needed_from="2025-01-01", needed_to="2025-01-10")
        _make_request(db, quantity=2, status="Borrowed",
                      needed_from="2025-01-05", needed_to="2025-01-15")

        repo = SQLiteRequestRepository(db)
        svc = AvailabilityService(repo)
        result = svc.calculate(
            equipment_id="EQ-001",
            needed_from="2025-01-08",
            needed_to="2025-01-12",
            quantity_total=5,
        )

        assert result.committed_quantity == 5
        assert result.available_quantity == 0

    def test_partial_overlap(self, db):
        """A request that does NOT overlap should not be counted."""
        _make_request(db, quantity=2, status="Approved",
                      needed_from="2025-01-01", needed_to="2025-01-05")

        repo = SQLiteRequestRepository(db)
        svc = AvailabilityService(repo)
        result = svc.calculate(
            equipment_id="EQ-001",
            needed_from="2025-01-06",  # starts after existing ends
            needed_to="2025-01-10",
            quantity_total=5,
        )

        assert result.committed_quantity == 0
        assert result.available_quantity == 5

    def test_adjacent_dates_are_not_overlapping(self, db):
        """Requests with end_a == start_b do NOT overlap (exclusive end)."""
        _make_request(db, quantity=3, status="Approved",
                      needed_from="2025-01-01", needed_to="2025-01-05")

        repo = SQLiteRequestRepository(db)
        svc = AvailabilityService(repo)
        result = svc.calculate(
            equipment_id="EQ-001",
            needed_from="2025-01-05",
            needed_to="2025-01-10",
            quantity_total=5,
        )
        # Note: per spec, overlap is start_a <= end_b AND start_b <= end_a
        # So needed_from=2025-01-05 and needed_to_existing=2025-01-05 DOES overlap
        # (the equipment is needed on Jan 5 and existing ends on Jan 5)
        assert result.committed_quantity == 3

    def test_pending_requests_show_as_competing_not_committed(self, db):
        _make_request(db, quantity=2, status="Pending",
                      needed_from="2025-01-01", needed_to="2025-01-10")

        repo = SQLiteRequestRepository(db)
        svc = AvailabilityService(repo)
        result = svc.calculate(
            equipment_id="EQ-001",
            needed_from="2025-01-05",
            needed_to="2025-01-08",
            quantity_total=5,
        )

        assert result.committed_quantity == 0
        assert result.available_quantity == 5
        assert len(result.competing_pending_requests) == 1
        assert result.competing_pending_requests[0].quantity == 2

    def test_exclude_request_from_conflict(self, db):
        r = _make_request(db, quantity=3, status="Approved",
                          needed_from="2025-01-01", needed_to="2025-01-10")

        repo = SQLiteRequestRepository(db)
        svc = AvailabilityService(repo)
        result = svc.calculate(
            equipment_id="EQ-001",
            needed_from="2025-01-01",
            needed_to="2025-01-10",
            quantity_total=5,
            exclude_request_id=r.id,
        )

        assert result.committed_quantity == 0
        assert result.available_quantity == 5

    def test_cancelled_rejected_not_counted(self, db):
        _make_request(db, quantity=5, status="Cancelled",
                      needed_from="2025-01-01", needed_to="2025-01-10")
        _make_request(db, quantity=5, status="Rejected",
                      needed_from="2025-01-01", needed_to="2025-01-10")

        repo = SQLiteRequestRepository(db)
        svc = AvailabilityService(repo)
        result = svc.calculate(
            equipment_id="EQ-001",
            needed_from="2025-01-05",
            needed_to="2025-01-08",
            quantity_total=5,
        )

        assert result.committed_quantity == 0
        assert result.available_quantity == 5

    def test_returned_requests_not_counted(self, db):
        _make_request(db, quantity=5, status="Returned",
                      needed_from="2025-01-01", needed_to="2025-01-10")

        repo = SQLiteRequestRepository(db)
        svc = AvailabilityService(repo)
        result = svc.calculate(
            equipment_id="EQ-001",
            needed_from="2025-01-05",
            needed_to="2025-01-08",
            quantity_total=5,
        )

        assert result.committed_quantity == 0
        assert result.available_quantity == 5

"""Integration tests for the requests API endpoints."""
from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

from app.core.database import Base
from app.core.deps import get_db, get_current_user
from app.models.equipment import EquipmentModel
from app.auth.session import SessionData

@pytest.fixture
def client(tmp_path):
    """Return a TestClient backed by a fresh temporary SQLite DB file."""
    db_file = tmp_path / "test.db"
    test_db_url = f"sqlite:///{db_file}"

    engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    import app.models.equipment
    import app.models.request
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    from app.main import app
    app.dependency_overrides[get_db] = override_get_db

    # Default to user
    def override_get_current_user():
        return SessionData(user_email='test@example.com', user_name='Test User', user_oid='abc', is_manager=False)
        
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Seed test equipment into the test DB
    session = TestSession()
    session.add(EquipmentModel(
        equipment_id="EQ-TEST-001",
        equipment_name="Test Oscilloscope",
        category="Measurement",
        description="For testing",
        quantity_total=3,
        unit="unit",
        location="Lab A",
    ))
    session.commit()
    session.close()

    from app.core.config import settings
    old_backend = settings.DATA_BACKEND
    settings.DATA_BACKEND = "sqlite"

    with patch("app.main._seed_if_empty", return_value=None), \
         patch("app.main.create_all_tables", return_value=None):
        with TestClient(app) as c:
            yield c

    settings.DATA_BACKEND = old_backend
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

def set_manager_role(app):
    def override_get_current_user():
        return SessionData(user_email='manager@example.com', user_name='Manager', user_oid='xyz', is_manager=True)
    app.dependency_overrides[get_current_user] = override_get_current_user

def set_user_role(app):
    def override_get_current_user():
        return SessionData(user_email='test@example.com', user_name='Test User', user_oid='abc', is_manager=False)
    app.dependency_overrides[get_current_user] = override_get_current_user

class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

class TestGraphHealth:
    def test_graph_health_not_configured(self, client):
        resp = client.get("/api/health/integrations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["microsoft_graph"]["status"] == "not_configured"

class TestGeminiHealth:
    def test_gemini_health_not_configured(self, client, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
        resp = client.get("/api/health/integrations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["gemini"]["status"] == "not_configured"


class TestEquipmentEndpoints:
    def test_list_equipment(self, client):
        resp = client.get("/api/equipment")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["equipment_id"] == "EQ-TEST-001"

    def test_get_equipment_by_id(self, client):
        resp = client.get("/api/equipment/EQ-TEST-001")
        assert resp.status_code == 200
        assert resp.json()["equipment_name"] == "Test Oscilloscope"

    def test_get_nonexistent_equipment(self, client):
        resp = client.get("/api/equipment/NONEXISTENT")
        assert resp.status_code == 404

    def test_search_equipment(self, client):
        resp = client.get("/api/equipment?q=Oscillo")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_availability(self, client):
        resp = client.get(
            "/api/equipment/EQ-TEST-001/availability",
            params={"needed_from": "2025-06-01", "needed_to": "2025-06-10"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["available_quantity"] == 3
        assert data["committed_quantity"] == 0

class TestCreateRequest:
    def _payload(self, **overrides):
        base = {
            "project": "Research Project",
            "equipment_id": "EQ-TEST-001",
            "quantity": 1,
            "needed_from": "2025-06-01",
            "needed_to": "2025-06-10",
            "purpose": "Research experiment",
        }
        base.update(overrides)
        return base

    def test_create_request_success(self, client):
        from app.main import app
        set_user_role(app)
        resp = client.post("/api/requests", json=self._payload())
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "Pending"
        assert data["display_id"].startswith("REQ-")
        assert data["equipment_id"] == "EQ-TEST-001"
        assert data["requester_name"] == "Test User"

    def test_create_request_invalid_dates(self, client):
        resp = client.post(
            "/api/requests",
            json=self._payload(needed_from="2025-06-10", needed_to="2025-06-01"),
        )
        assert resp.status_code == 422

    def test_create_request_zero_quantity(self, client):
        resp = client.post(
            "/api/requests",
            json=self._payload(quantity=0),
        )
        assert resp.status_code == 422

    def test_create_request_nonexistent_equipment(self, client):
        resp = client.post(
            "/api/requests",
            json=self._payload(equipment_id="FAKE-EQ"),
        )
        assert resp.status_code == 404

class TestRequestWorkflow:
    def _create(self, client):
        from app.main import app
        set_user_role(app)
        payload = {
            "project": "Research Project",
            "equipment_id": "EQ-TEST-001",
            "quantity": 1,
            "needed_from": "2025-07-01",
            "needed_to": "2025-07-10",
            "purpose": "Research experiment",
        }
        resp = client.post("/api/requests", json=payload)
        assert resp.status_code == 201
        return resp.json()

    def test_full_workflow(self, client):
        from app.main import app
        req = self._create(client)
        req_id = req["id"]
        assert req["status"] == "Pending"

        set_manager_role(app)
        resp = client.post(f"/api/manager/requests/{req_id}/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "Approved"

        resp = client.post(f"/api/manager/requests/{req_id}/mark-borrowed")
        assert resp.status_code == 200
        assert resp.json()["status"] == "Borrowed"

        set_user_role(app)
        resp = client.post(f"/api/requests/{req_id}/mark-returned")
        assert resp.status_code == 200
        assert resp.json()["status"] == "Returned"

    def test_user_can_cancel_pending(self, client):
        from app.main import app
        req = self._create(client)
        set_user_role(app)
        resp = client.post(f"/api/requests/{req['id']}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "Cancelled"

    def test_manager_can_reject(self, client):
        from app.main import app
        req = self._create(client)
        set_manager_role(app)
        resp = client.post(
            f"/api/manager/requests/{req['id']}/reject",
            json={"reason": "Insufficient details"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "Rejected"

    def test_nonmanager_cannot_approve(self, client):
        from app.main import app
        req = self._create(client)
        set_user_role(app)
        resp = client.post(f"/api/manager/requests/{req['id']}/approve")
        assert resp.status_code == 403

    def test_get_my_requests(self, client):
        from app.main import app
        self._create(client)
        set_user_role(app)
        resp = client.get("/api/requests/mine")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_manager_summary(self, client):
        from app.main import app
        self._create(client)
        set_manager_role(app)
        resp = client.get("/api/manager/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "pending_count" in data
        assert data["total_requests"] >= 1

class TestAgentEndpoint:
    def test_help_intent(self, client):
        resp = client.post("/api/agent/message", json={"message": "giúp tôi"})
        assert resp.status_code == 200
        assert "reply" in resp.json()

    def test_borrow_intent_returns_action(self, client):
        resp = client.post("/api/agent/message", json={"message": "tôi muốn mượn thiết bị"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("action") is not None
        assert data["action"]["type"] == "show_borrow_form"

    def test_search_intent_lists_equipment(self, client):
        resp = client.post("/api/agent/message", json={"message": "cho tôi xem danh sách thiết bị"})
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "EQ-TEST-001" in data["reply"] or "Test Oscilloscope" in data["reply"]

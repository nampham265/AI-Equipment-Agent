"""End-to-end API tests using the Excel backend."""
from __future__ import annotations

import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.auth.session import SessionData
from app.core.deps import get_current_user


@pytest.fixture
def excel_client(tmp_path):
    """TestClient configured with a temporary copy of the Excel workbook."""
    real_path = settings.resolved_excel_path
    assert real_path.exists(), f"Source workbook must exist at {real_path}"
    
    test_excel = tmp_path / "equipment_agent.xlsx"
    shutil.copyfile(real_path, test_excel)

    old_backend = settings.DATA_BACKEND
    old_excel_path = settings.EXCEL_DATA_PATH

    settings.DATA_BACKEND = "excel"
    settings.EXCEL_DATA_PATH = str(test_excel)

    from app.main import app

    def override_user():
        return SessionData(
            user_email="user@company.com",
            user_name="Nguyen Van User",
            user_oid="oid-user-123",
            is_manager=False,
        )

    app.dependency_overrides[get_current_user] = override_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    settings.DATA_BACKEND = old_backend
    settings.EXCEL_DATA_PATH = old_excel_path


def set_manager(app):
    def override_manager():
        return SessionData(
            user_email="manager@company.com",
            user_name="Manager Tran",
            user_oid="oid-mgr-456",
            is_manager=True,
        )
    app.dependency_overrides[get_current_user] = override_manager


def set_user(app):
    def override_user():
        return SessionData(
            user_email="user@company.com",
            user_name="Nguyen Van User",
            user_oid="oid-user-123",
            is_manager=False,
        )
    app.dependency_overrides[get_current_user] = override_user


class TestExcelIntegrationHealth:
    def test_health_reports_excel_connected(self, excel_client):
        resp = excel_client.get("/api/health/integrations")
        assert resp.status_code == 200
        data = resp.json()
        assert "excel" in data
        assert data["excel"]["status"] == "connected"


class TestExcelEquipmentAPI:
    def test_list_equipment_from_excel(self, excel_client):
        resp = excel_client.get("/api/equipment")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        # Real inventory has TU1-001
        assert any(i["equipment_id"] == "TU1-001" for i in items)

    def test_get_equipment_by_id(self, excel_client):
        resp = excel_client.get("/api/equipment/TU1-001")
        assert resp.status_code == 200
        item = resp.json()
        assert item["equipment_id"] == "TU1-001"
        assert item["quantity_total"] > 0


class TestExcelWorkflowAndPriorityReview:
    def test_full_request_and_manager_priority_review(self, excel_client):
        from app.main import app

        set_user(app)
        # 1. Create request
        payload = {
            "project": "Dự án Radar",
            "equipment_id": "TU1-001",
            "quantity": 2,
            "needed_from": "2026-06-01",
            "needed_to": "2026-06-10",
            "purpose": "Thử nghiệm mạch kết nối",
        }
        res_create = excel_client.post("/api/requests", json=payload)
        assert res_create.status_code == 201
        created = res_create.json()
        
        req_id = created["id"]
        assert created["status"] == "Pending"
        assert created["display_id"].startswith("REQ-")
        assert created["final_priority_level"] is None
        assert created["priority_level"] in ("High", "Medium", "Low", "Needs review", "Critical")
        original_ai_priority = created["priority_level"]
        original_ai_reason = created["priority_reason"]

        # 2. Non-manager cannot review priority
        res_unauth = excel_client.patch(
            f"/api/manager/requests/{req_id}/priority",
            json={"final_priority_level": "High"},
        )
        assert res_unauth.status_code == 403

        # 3. Manager reviews priority independently
        set_manager(app)
        res_priority = excel_client.patch(
            f"/api/manager/requests/{req_id}/priority",
            json={"final_priority_level": "High"},
        )
        assert res_priority.status_code == 200
        reviewed = res_priority.json()
        assert reviewed["final_priority_level"] == "High"
        assert reviewed["priority_reviewed_by"] == "manager@company.com"
        assert reviewed["priority_reviewed_at"] is not None
        # Verify AI recommendation was NOT modified
        assert reviewed["priority_level"] == original_ai_priority
        assert reviewed["priority_reason"] == original_ai_reason
        # Request is still Pending
        assert reviewed["status"] == "Pending"

        # 4. Manager approves request
        res_approve = excel_client.post(f"/api/manager/requests/{req_id}/approve")
        assert res_approve.status_code == 200
        assert res_approve.json()["status"] == "Approved"

        # 5. Manager marks as borrowed
        res_borrowed = excel_client.post(f"/api/manager/requests/{req_id}/mark-borrowed")
        assert res_borrowed.status_code == 200
        assert res_borrowed.json()["status"] == "Borrowed"

        # 6. User marks as returned
        set_user(app)
        res_returned = excel_client.post(f"/api/requests/{req_id}/mark-returned")
        assert res_returned.status_code == 200
        assert res_returned.json()["status"] == "Returned"

        # 7. Check my requests contains the returned request
        res_mine = excel_client.get("/api/requests/mine")
        assert res_mine.status_code == 200
        mine = res_mine.json()
        assert any(r["id"] == req_id for r in mine)

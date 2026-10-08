"""Full End-to-End Role-Based MVP Scenario Test (Section 26).

Verifies the complete flow across USER, MANAGER, and ADMIN roles:
1. Admin logs in as nampham.31231023820@st.ueh.edu.vn, adds a MANAGER and a USER.
2. USER logs in, searches equipment, creates request, sees own request.
3. MANAGER logs in, reviews AI priority, sets FinalPriorityLevel, approves request.
4. USER logs in, verifies updated status and FinalPriorityLevel.
5. Security tests: verify API rejects USER approving request, USER modifying priority,
   MANAGER accessing user management, deactivation blocking access, and last-admin guard.
"""
from __future__ import annotations

import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.repositories.factory as factory


@pytest.fixture
def scenario_app(tmp_path, monkeypatch):
    """Create a temporary copy of equipment_agent.xlsx and configure app to use it."""
    orig_path = Path("data/equipment_agent.xlsx")
    test_wb_path = tmp_path / "scenario_equipment_agent.xlsx"
    shutil.copyfile(orig_path, test_wb_path)

    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_BACKEND", "excel")
    monkeypatch.setattr(settings, "EXCEL_DATA_PATH", str(test_wb_path))
    monkeypatch.setattr(settings, "APP_ENV", "development")

    factory._excel_user_repo = None
    factory._excel_equipment_repo = None
    factory._excel_request_repo = None

    client = TestClient(app)
    yield client

    factory._excel_user_repo = None
    factory._excel_equipment_repo = None
    factory._excel_request_repo = None


class TestFullScenarioSection26:
    def test_complete_role_based_workflow(self, scenario_app):
        client = scenario_app

        # -------------------------------------------------------------
        # STEP 1: Admin logs in as nampham.31231023820@st.ueh.edu.vn
        # -------------------------------------------------------------
        admin_login = client.post("/auth/dev-login", json={"email": "nampham.31231023820@st.ueh.edu.vn"})
        assert admin_login.status_code == 200
        admin_data = admin_login.json()
        assert admin_data["role"] == "ADMIN"
        assert admin_data["is_admin"] is True

        # Check /api/me
        me_admin = client.get("/api/me")
        assert me_admin.status_code == 200
        assert me_admin.json()["role"] == "ADMIN"
        assert me_admin.json()["is_admin"] is True

        # Admin adds a MANAGER
        add_mgr = client.post("/api/admin/users", json={
            "user_email": "manager_scenario@company.com",
            "user_name": "Quản lý Demo",
            "role": "MANAGER",
        })
        assert add_mgr.status_code == 201
        assert add_mgr.json()["role"] == "MANAGER"

        # Admin adds a USER
        add_usr = client.post("/api/admin/users", json={
            "user_email": "user_scenario@company.com",
            "user_name": "Kỹ sư Demo",
            "role": "USER",
        })
        assert add_usr.status_code == 201
        assert add_usr.json()["role"] == "USER"

        # Verify all users in sheet
        users_list = client.get("/api/admin/users")
        assert users_list.status_code == 200
        emails = [u["user_email"] for u in users_list.json()]
        assert "nampham.31231023820@st.ueh.edu.vn" in emails
        assert "manager_scenario@company.com" in emails
        assert "user_scenario@company.com" in emails

        # -------------------------------------------------------------
        # STEP 2: USER logs in, searches equipment, creates request
        # -------------------------------------------------------------
        user_login = client.post("/auth/dev-login", json={"email": "user_scenario@company.com"})
        assert user_login.status_code == 200
        user_info = user_login.json()
        assert user_info["role"] == "USER"
        assert user_info["is_admin"] is False
        assert user_info["is_manager"] is False

        # USER searches equipment
        eq_search = client.get("/api/equipment")
        assert eq_search.status_code == 200
        equipment_list = eq_search.json()
        assert len(equipment_list) > 0
        target_eq = equipment_list[0]
        eq_id = target_eq["equipment_id"]

        # USER creates request
        create_req = client.post("/api/requests", json={
            "project": "Dự án Nâng cấp IoT",
            "equipment_id": eq_id,
            "quantity": 1,
            "needed_from": "2025-09-01",
            "needed_to": "2025-09-10",
            "purpose": "Thử nghiệm cảm biến",
        })
        assert create_req.status_code == 201
        created_data = create_req.json()
        req_id = created_data["id"]
        assert created_data["status"] == "Pending"
        assert created_data["requester_email"] == "user_scenario@company.com"
        assert created_data["requester_name"] == "Kỹ sư Demo"
        assert created_data["final_priority_level"] is None
        assert created_data["priority_level"] is not None

        # USER views own requests
        my_reqs = client.get("/api/requests/mine")
        assert my_reqs.status_code == 200
        assert any(r["id"] == req_id for r in my_reqs.json())

        # -------------------------------------------------------------
        # STEP 3: USER tries unauthorized actions (Security verification)
        # -------------------------------------------------------------
        # USER cannot approve
        assert client.post(f"/api/manager/requests/{req_id}/approve").status_code == 403
        # USER cannot review priority
        assert client.patch(f"/api/manager/requests/{req_id}/priority", json={"final_priority_level": "High"}).status_code == 403
        # USER cannot access admin users
        assert client.get("/api/admin/users").status_code == 403
        # USER cannot create users
        assert client.post("/api/admin/users", json={"user_email": "hack@company.com", "user_name": "Hacker", "role": "USER"}).status_code == 403

        # -------------------------------------------------------------
        # STEP 4: MANAGER logs in, reviews AI priority, approves request
        # -------------------------------------------------------------
        mgr_login = client.post("/auth/dev-login", json={"email": "manager_scenario@company.com"})
        assert mgr_login.status_code == 200
        mgr_info = mgr_login.json()
        assert mgr_info["role"] == "MANAGER"
        assert mgr_info["is_manager"] is True
        assert mgr_info["is_admin"] is False

        # MANAGER cannot access admin user management
        assert client.get("/api/admin/users").status_code == 403

        # MANAGER views pending requests
        mgr_reqs = client.get("/api/manager/requests?status=Pending")
        assert mgr_reqs.status_code == 200
        assert any(r["id"] == req_id for r in mgr_reqs.json())

        # MANAGER sets final priority level
        prio_patch = client.patch(f"/api/manager/requests/{req_id}/priority", json={
            "final_priority_level": "High"
        })
        assert prio_patch.status_code == 200
        prio_data = prio_patch.json()
        assert prio_data["final_priority_level"] == "High"
        assert prio_data["priority_reviewed_by"] == "manager_scenario@company.com"
        assert prio_data["priority_reviewed_at"] is not None
        # AI fields remain intact
        assert prio_data["priority_level"] is not None
        assert prio_data["priority_reason"] is not None

        # MANAGER approves request
        approve_res = client.post(f"/api/manager/requests/{req_id}/approve")
        assert approve_res.status_code == 200
        assert approve_res.json()["status"] == "Approved"

        # -------------------------------------------------------------
        # STEP 5: USER logs in again, verifies updated status & priority
        # -------------------------------------------------------------
        user_login2 = client.post("/auth/dev-login", json={"email": "user_scenario@company.com"})
        assert user_login2.status_code == 200

        my_reqs2 = client.get("/api/requests/mine")
        assert my_reqs2.status_code == 200
        my_updated_req = next(r for r in my_reqs2.json() if r["id"] == req_id)
        assert my_updated_req["status"] == "Approved"
        assert my_updated_req["final_priority_level"] == "High"
        assert my_updated_req["priority_reviewed_by"] == "manager_scenario@company.com"

        # -------------------------------------------------------------
        # STEP 6: Admin guards and Deactivation test
        # -------------------------------------------------------------
        admin_login2 = client.post("/auth/dev-login", json={"email": "nampham.31231023820@st.ueh.edu.vn"})
        assert admin_login2.status_code == 200

        # Demote any other admins in the test workbook to ensure nampham is the last active admin
        client.patch("/api/admin/users/phamngochainam25@gmail.com/role", json={"role": "USER"})

        # Admin cannot demote last admin
        demote_res = client.patch("/api/admin/users/nampham.31231023820@st.ueh.edu.vn/role", json={"role": "MANAGER"})
        assert demote_res.status_code == 400

        # Admin cannot deactivate last admin
        deact_res = client.patch("/api/admin/users/nampham.31231023820@st.ueh.edu.vn/active", json={"is_active": False})
        assert deact_res.status_code == 400

        # Admin deactivates USER
        deact_user = client.patch("/api/admin/users/user_scenario@company.com/active", json={"is_active": False})
        assert deact_user.status_code == 200
        assert deact_user.json()["is_active"] is False

        # Deactivated user cannot log in
        blocked_login = client.post("/auth/dev-login", json={"email": "user_scenario@company.com"})
        assert blocked_login.status_code == 403
        assert "vô hiệu hóa" in blocked_login.json()["detail"]

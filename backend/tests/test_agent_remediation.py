"""Automated test suite verifying Agent Core Remediation and Stabilization requirements.

Covers all test cases from Sections 6, 7, 10, 12, 14, 15, 16, 18, 19, 20, 24, 25, 27, 40, 41, 42.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.factory import get_request_repo, get_user_repo
from app.schemas.requests import RequestRead


@pytest.fixture
def admin_client():
    client = TestClient(app)
    res = client.post("/auth/dev-login", json={"email": "nampham.31231023820@st.ueh.edu.vn"})
    assert res.status_code == 200
    return client


@pytest.fixture
def manager_client(admin_client):
    client = TestClient(app)
    m_email = "test.manager@company.com"
    admin_client.post(
        "/api/admin/users",
        json={"user_email": m_email, "user_name": "Test Manager", "role": "MANAGER"},
    )
    res = client.post("/auth/dev-login", json={"email": m_email})
    assert res.status_code == 200
    return client


@pytest.fixture
def user_client(admin_client):
    client = TestClient(app)
    u_email = "regular.dev.user@company.com"
    admin_client.post(
        "/api/admin/users",
        json={"user_email": u_email, "user_name": "Dev User", "role": "USER"},
    )
    res = client.post("/auth/dev-login", json={"email": u_email})
    assert res.status_code == 200
    return client


# ---------------------------------------------------------------------------
# Section 12 & 40: Relevance Threshold & Not Found (CANInterface XYZ)
# ---------------------------------------------------------------------------

def test_unknown_equipment_returns_not_found(user_client):
    """'Kho có CANInterface XYZ không?'
    Expected structured interpretation:
    intent = equipment_exists
    entity = "CANInterface XYZ"
    The search tool MUST receive only the extracted equipment entity/query.
    Reply: "Không tìm thấy thiết bị CANInterface XYZ trong dữ liệu hiện tại."
    Must not return: "Không tìm thấy thiết bị phù hợp với 'Kho có CANInterface XYZ không?'"
    """
    res = user_client.post(
        "/api/agent/message",
        json={"message": "Kho có CANInterface XYZ không?", "conversation_id": "conv-can-xyz"},
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]
    trace = data.get("trace", {})

    # Check structured interpretation
    assert trace.get("intent") == "equipment_exists"
    assert trace.get("entities", {}).get("entity") == "CANInterface XYZ"
    assert trace.get("selected_tool") == "search_equipment"
    assert trace.get("tool_arguments", {}).get("query") == "CANInterface XYZ"

    # Check reply format
    assert reply == "Không tìm thấy thiết bị CANInterface XYZ trong dữ liệu hiện tại."
    assert "Kho có CANInterface XYZ không?" not in reply
    assert "phù hợp với" not in reply

    # Must NOT return any unrelated equipment
    assert "EBS-" not in reply
    assert "CSW-" not in reply
    assert "TU1-" not in reply


def test_tu1_001_regression_queries(user_client):
    """Regression test suite for:
    - 'Kho có TU1-001 không?'
    - 'TU1-001 còn bao nhiêu cái?'
    - 'TU1-001 nằm ở đâu?'
    - 'Cho mình thông tin về TU1-001.'
    """
    conv_id = "conv-tu1-001-regression"

    # 1. Kho có TU1-001 không?
    r1 = user_client.post(
        "/api/agent/message",
        json={"message": "Kho có TU1-001 không?", "conversation_id": conv_id},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    t1 = d1.get("trace", {})
    assert t1.get("intent") == "equipment_exists"
    assert t1.get("entities", {}).get("entity") == "TU1-001"
    assert t1.get("tool_arguments", {}).get("query") == "TU1-001"
    assert "Có" in d1["reply"]
    assert "TU1-001" in d1["reply"]
    assert "37" in d1["reply"]
    assert "Tủ 1" in d1["reply"]

    # 2. TU1-001 còn bao nhiêu cái?
    r2 = user_client.post(
        "/api/agent/message",
        json={"message": "TU1-001 còn bao nhiêu cái?", "conversation_id": conv_id},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    t2 = d2.get("trace", {})
    assert t2.get("intent") == "equipment_count"
    assert "37" in d2["reply"]
    assert "Tủ 1" in d2["reply"]

    # 3. TU1-001 nằm ở đâu?
    r3 = user_client.post(
        "/api/agent/message",
        json={"message": "TU1-001 nằm ở đâu?", "conversation_id": conv_id},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    t3 = d3.get("trace", {})
    assert t3.get("intent") == "equipment_detail"
    assert "Tủ 1" in d3["reply"]

    # 4. Cho mình thông tin về TU1-001.
    r4 = user_client.post(
        "/api/agent/message",
        json={"message": "Cho mình thông tin về TU1-001.", "conversation_id": conv_id},
    )
    assert r4.status_code == 200
    d4 = r4.json()
    t4 = d4.get("trace", {})
    assert t4.get("intent") == "equipment_detail"
    assert "Thông tin thiết bị" in d4["reply"]
    assert "TU1-001" in d4["reply"]
    assert "37" in d4["reply"]


# ---------------------------------------------------------------------------
# Section 10 & 40: Multi-constraint hard filter & semantic ranking
# ---------------------------------------------------------------------------

def test_interface_board_in_tu_1(user_client):
    """'Thiết bị nào ở Tủ 1 phù hợp để làm interface board?'
    Must match TU1-001, TU1-015 (header connectors for interface board).
    Must NOT match TU1-041 (glue gun).
    Must NOT return EBS or CSW equipment.
    """
    res = user_client.post(
        "/api/agent/message",
        json={"message": "Thiết bị nào ở Tủ 1 phù hợp để làm interface board?", "conversation_id": "conv-if-board"},
    )
    assert res.status_code == 200
    reply = res.json()["reply"]
    assert "TU1-001" in reply or "TU1-015" in reply
    # Must reject glue gun
    assert "TU1-041" not in reply
    assert "Súng bắn keo" not in reply
    # Must reject non-Tủ 1 equipment
    assert "CSW-" not in reply
    assert "EBS-" not in reply


# ---------------------------------------------------------------------------
# Section 14 & 40: Attribute extraction (Color: black)
# ---------------------------------------------------------------------------

def test_black_connector_search(user_client):
    """'Cho mình cái connector màu đen.'
    Must return connector + black candidates (e.g. TU1-001, TU1-003, TU1-005).
    """
    res = user_client.post(
        "/api/agent/message",
        json={"message": "Cho mình cái connector màu đen.", "conversation_id": "conv-black-conn"},
    )
    assert res.status_code == 200
    reply = res.json()["reply"]
    # Check that at least one genuine black connector is returned
    assert any(eq_id in reply for eq_id in ["TU1-001", "TU1-003", "TU1-005", "EBS-030", "EBS-037"])


# ---------------------------------------------------------------------------
# Section 15 & 16: Deterministic numeric calculation & availability
# ---------------------------------------------------------------------------

def test_quantity_sufficiency_shortage_calculation(user_client):
    """'TU1-001 có đủ 50 cái không?'
    Total = 37. Shortage = 13.
    Expected: Kho hiện ghi nhận 37 cái TU1-001, nên không đủ 50 cái. Số lượng thiếu là 13 cái.
    No hallucination of 19!
    """
    res = user_client.post(
        "/api/agent/message",
        json={"message": "TU1-001 có đủ 50 cái không?", "conversation_id": "conv-suff-50"},
    )
    assert res.status_code == 200
    reply = res.json()["reply"]
    assert "37" in reply
    assert "50" in reply
    assert "13" in reply
    assert "không đủ" in reply.lower() or "thiếu" in reply.lower()
    assert "19" not in reply


def test_quantity_sufficiency_without_date_range(user_client):
    """'Mình cần 10 cái TU1-001, kho có đủ không?'
    When no date range is provided, total quantity (37) cannot be claimed as confirmed available.
    Expected: Kho hiện ghi nhận tổng cộng 37 cái TU1-001. Tuy nhiên, hệ thống hiện chưa có đủ dữ liệu mượn/trả...
    """
    res = user_client.post(
        "/api/agent/message",
        json={"message": "Mình cần 10 cái TU1-001, kho có đủ không?", "conversation_id": "conv-suff-10"},
    )
    assert res.status_code == 200
    reply = res.json()["reply"]
    assert "37" in reply
    assert "chưa có đủ dữ liệu" in reply or "khoảng thời gian" in reply


# ---------------------------------------------------------------------------
# Section 18 & 40: Damage / condition questions routing
# ---------------------------------------------------------------------------

def test_condition_damage_reporting_flow(user_client):
    """'Sau khi trả thiết bị, nếu phát hiện hư hỏng thì hệ thống có thể báo cho quản lý không?'
    Must give capability response, NOT equipment search and NOT borrow form.
    """
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Sau khi trả thiết bị, nếu phát hiện hư hỏng thì hệ thống có thể báo cho quản lý không?",
            "conversation_id": "conv-damage-report",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is None
    reply = data["reply"]
    assert "chưa hỗ trợ" in reply
    assert "hư hỏng" in reply or "báo hỏng" in reply or "Quản lý" in reply


# ---------------------------------------------------------------------------
# Section 40: Cross-project scheduling conflict inquiry
# ---------------------------------------------------------------------------

def test_scheduling_conflict_inquiry(user_client):
    """'Project A cần TU1-001 từ 10/10 đến 12/10, Project B cũng cần. Có thể sắp xếp lịch không?'
    Expected: planning/analysis response, not borrow form.
    """
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Project A cần TU1-001 từ 10/10 đến 12/10, Project B cũng cần. Có thể sắp xếp lịch không?",
            "conversation_id": "conv-schedule-plan",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is None
    reply = data["reply"]
    assert "chưa hỗ trợ" in reply or "Quản lý" in reply
    assert "lịch" in reply.lower()


# ---------------------------------------------------------------------------
# Section 20 & 40: Borrow request with auto-approval request
# ---------------------------------------------------------------------------

def test_borrow_request_cannot_auto_approve(user_client):
    """'Mình cần mượn 5 cái TU1-001, bạn duyệt luôn giúp mình.'
    Must open borrow form, but must explicitly remind user that AI cannot auto-approve.
    """
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Mình cần mượn 5 cái TU1-001, bạn duyệt luôn giúp mình.",
            "conversation_id": "conv-auto-approve-req",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is not None
    assert data["action"]["type"] == "show_borrow_form"
    reply = data["reply"]
    assert "không có quyền tự phê duyệt" in reply or "Quản lý" in reply


# ---------------------------------------------------------------------------
# Section 24, 25, 41: Full Manager Workflow in Chat
# ---------------------------------------------------------------------------

def test_manager_full_chat_workflow(manager_client, user_client):
    """Full Manager sequence:
    1. Pending count
    2. Pending list
    3. Đơn thứ 1 là của ai?
    4. AI đề xuất mức ưu tiên gì cho đơn này? (Inquiry: must NOT mutate priority)
    5. Tôi đổi priority thành High (Mutation: FinalPriorityLevel = High, PriorityLevel intact)
    6. Duyệt đơn này (Approve)
    """
    # Step 0: Ensure a pending request created by a user exists
    req_repo = get_request_repo()
    from datetime import datetime, timezone
    req = req_repo.create(RequestRead(
        id=0,
        requester_name="Dev User",
        requester_email="regular.dev.user@company.com",
        project="Test Project X",
        equipment_id="TU1-002",
        equipment_name="Conn header R/A 10pos 4.2mm",
        quantity=2,
        needed_from="2026-11-01",
        needed_to="2026-11-05",
        purpose="Testing manager workflow in agent",
        priority_level="Medium",
        priority_reason="Standard testing priority",
        status="Pending",
        created_at=datetime.now(timezone.utc).isoformat(),
        modified_at=datetime.now(timezone.utc).isoformat(),
    ))
    target_id = req.id
    conv_id = f"conv-mgr-workflow-{target_id}"

    # Step 1: Manager asks pending count
    res1 = manager_client.post(
        "/api/agent/message",
        json={"message": "Có bao nhiêu đơn đang chờ duyệt?", "conversation_id": conv_id},
    )
    assert res1.status_code == 200
    assert "đơn" in res1.json()["reply"]

    # Step 2: Manager asks pending list
    res2 = manager_client.post(
        "/api/agent/message",
        json={"message": "Cho mình xem các đơn đang chờ duyệt.", "conversation_id": conv_id},
    )
    assert res2.status_code == 200
    reply2 = res2.json()["reply"]
    assert "đơn" in reply2.lower()

    # Step 3: Manager asks about target request
    res3 = manager_client.post(
        "/api/agent/message",
        json={"message": f"Đơn #{target_id} là của ai?", "conversation_id": conv_id},
    )
    assert res3.status_code == 200
    assert "Dev User" in res3.json()["reply"] or "tạo bởi" in res3.json()["reply"]

    # Step 4: Manager asks what AI recommended for priority
    res4 = manager_client.post(
        "/api/agent/message",
        json={"message": "AI đề xuất mức ưu tiên gì cho đơn này?", "conversation_id": conv_id},
    )
    assert res4.status_code == 200
    reply4 = res4.json()["reply"]
    assert "AI đề xuất" in reply4 or "ưu tiên" in reply4.lower()
    # Check that database was NOT mutated
    db_req_after4 = req_repo.get_by_id(target_id)
    assert db_req_after4.priority_level == "Medium"
    assert db_req_after4.final_priority_level is None or db_req_after4.final_priority_level == ""

    # Step 5: Manager changes priority to High
    res5 = manager_client.post(
        "/api/agent/message",
        json={"message": "Tôi đổi priority thành High", "conversation_id": conv_id},
    )
    assert res5.status_code == 200
    assert "Đã cập nhật mức ưu tiên" in res5.json()["reply"]
    # Check database: FinalPriorityLevel is High, PriorityLevel is still Medium!
    db_req_after5 = req_repo.get_by_id(target_id)
    assert db_req_after5.final_priority_level == "High"
    assert db_req_after5.priority_level == "Medium"
    assert db_req_after5.priority_reason == "Standard testing priority"

    # Step 6: Manager approves request
    res6 = manager_client.post(
        "/api/agent/message",
        json={"message": "Duyệt đơn này", "conversation_id": conv_id},
    )
    assert res6.status_code == 200
    assert "Đã phê duyệt" in res6.json()["reply"]
    db_req_after6 = req_repo.get_by_id(target_id)
    assert db_req_after6.status == "Approved"


# ---------------------------------------------------------------------------
# Section 27: Self-Approval and Self-Rejection prevention
# ---------------------------------------------------------------------------

def test_manager_cannot_approve_own_request_in_chat(manager_client):
    """Manager creates a request, then tries to approve it via chat.
    Must be strictly blocked by server-side rule!
    """
    req_repo = get_request_repo()
    from datetime import datetime, timezone
    own_req = req_repo.create(RequestRead(
        id=0,
        requester_name="Test Manager",
        requester_email="test.manager@company.com",
        project="Manager's Own Project",
        equipment_id="TU1-001",
        equipment_name="Conn header SMD 24pos 3mm female",
        quantity=1,
        needed_from="2026-12-01",
        needed_to="2026-12-02",
        purpose="Self-request test",
        priority_level="Low",
        priority_reason="Self created",
        status="Pending",
        created_at=datetime.now(timezone.utc).isoformat(),
        modified_at=datetime.now(timezone.utc).isoformat(),
    ))
    conv_id = f"conv-self-approve-{own_req.id}"

    # Manager attempts to approve own request
    res = manager_client.post(
        "/api/agent/message",
        json={"message": f"Duyệt đơn #{own_req.id}", "conversation_id": conv_id},
    )
    assert res.status_code == 200
    reply = res.json()["reply"]
    assert "Không thể phê duyệt" in reply
    assert "chính mình" in reply


# ---------------------------------------------------------------------------
# Section 42: Admin vs Manager vs User RBAC
# ---------------------------------------------------------------------------

def test_admin_vs_manager_role_access(admin_client, manager_client, user_client):
    """Admin can list users in chat, Manager and User are blocked."""
    # Admin asks for users list
    res_admin = admin_client.post(
        "/api/agent/message",
        json={"message": "Danh sách user", "conversation_id": "conv-adm-users"},
    )
    assert res_admin.status_code == 200
    assert "Danh sách người dùng" in res_admin.json()["reply"]

    # Manager asks for users list -> blocked
    res_mgr = manager_client.post(
        "/api/agent/message",
        json={"message": "Danh sách user", "conversation_id": "conv-mgr-users"},
    )
    assert res_mgr.status_code == 200
    assert "Chỉ quản trị viên" in res_mgr.json()["reply"]

    # User asks for users list -> blocked
    res_usr = user_client.post(
        "/api/agent/message",
        json={"message": "Danh sách user", "conversation_id": "conv-usr-users"},
    )
    assert res_usr.status_code == 200
    assert "Chỉ quản trị viên" in res_usr.json()["reply"]


# ---------------------------------------------------------------------------
# Section I: Classification regression tests for Manager queries & domain separation
# ---------------------------------------------------------------------------

def test_manager_classification_regression(manager_client):
    """Verifies that manager request queries map to explicit request intents
    and equipment inventory queries map to equipment intents without cross-domain leakage.
    - "Ai là người request gần đây nhất?" -> recent_request
    - "Cho mình xem 5 request gần nhất." -> recent_requests
    - "Hiện có mấy đơn cần mình duyệt?" -> pending_request_count
    - "Cho mình xem các đơn đang chờ duyệt." -> pending_request_list
    - "Ai đang mượn thiết bị?" -> active_borrowers
    - "Có ai trả thiết bị trễ không?" -> overdue_loans
    - "Thiết bị nào đang ở Tủ 1?" -> equipment_search
    - "TU1-001 còn bao nhiêu cái?" -> equipment_count
    """
    cases = [
        ("Ai là người request gần đây nhất?", "recent_request", "get_recent_request"),
        ("Cho mình xem 5 request gần nhất.", "recent_requests", "get_recent_requests"),
        ("Hiện có mấy đơn cần mình duyệt?", "pending_request_count", "count_pending_requests"),
        ("Cho mình xem các đơn đang chờ duyệt.", "pending_request_list", "list_pending_requests"),
        ("Ai đang mượn thiết bị?", "active_borrowers", "get_active_borrowers"),
        ("Có ai trả thiết bị trễ không?", "overdue_loans", "get_overdue_loans"),
        ("Thiết bị nào đang ở Tủ 1?", "equipment_search", "search_equipment"),
        ("TU1-001 còn bao nhiêu cái?", "equipment_count", "get_equipment_count"),
    ]
    for idx, (query, expected_intent, expected_tool) in enumerate(cases):
        res = manager_client.post(
            "/api/agent/message",
            json={"message": query, "conversation_id": f"conv-cls-regression-{idx}"},
        )
        assert res.status_code == 200, f"Failed on query: {query}"
        trace = res.json().get("trace", {})
        assert trace.get("intent") == expected_intent, (
            f"Query '{query}' expected intent '{expected_intent}' but got '{trace.get('intent')}'"
        )
        assert trace.get("selected_tool") == expected_tool, (
            f"Query '{query}' expected tool '{expected_tool}' but got '{trace.get('selected_tool')}'"
        )


# ---------------------------------------------------------------------------
# Sections C, D, J: Recent requests & manager conversation context follow-ups
# ---------------------------------------------------------------------------

def test_recent_requests_and_context_followups(manager_client):
    """Tests recent request retrieval, list rendering, and follow-up resolution:
    - 'Ai là người request gần đây nhất?' -> recent_request (returns requester name, project, etc. NOT inventory)
    - 'Còn request trước đó thì sao?' -> resolves previous request chronologically
    - 'Cho mình xem các request gần đây' -> recent_requests table
    - 'Đơn thứ 2 là ai?' -> resolves requester of 2nd request
    - 'Cái đầu tiên của project nào?' -> resolves project of 1st request
    - 'Đơn này mượn gì?' -> resolves equipment name of 1st request
    - 'Đơn này ưu tiên gì?' -> resolves priority level & reason
    """
    from datetime import datetime, timezone, timedelta
    req_repo = get_request_repo()
    now = datetime.now(timezone.utc)

    # Seed 3 distinct requests with sequential timestamps
    r1 = req_repo.create(RequestRead(
        id=0,
        requester_name="Nguyen Van A",
        requester_email="vana@company.com",
        project="Project Alpha",
        equipment_id="TU1-001",
        equipment_name="Conn header SMD 24pos 3mm female",
        quantity=2,
        needed_from="2026-11-01",
        needed_to="2026-11-05",
        purpose="Testing Alpha hardware",
        priority_level="Medium",
        priority_reason="Standard test run for Project Alpha",
        status="Pending",
        created_at=(now - timedelta(hours=3)).isoformat(),
        modified_at=(now - timedelta(hours=3)).isoformat(),
    ))
    r2 = req_repo.create(RequestRead(
        id=0,
        requester_name="Tran Thi B",
        requester_email="thib@company.com",
        project="Project Beta",
        equipment_id="CSW-001",
        equipment_name="Switch SPST 12V",
        quantity=5,
        needed_from="2026-11-10",
        needed_to="2026-11-15",
        purpose="Beta board integration",
        priority_level="High",
        priority_reason="Crucial beta phase integration",
        status="Pending",
        created_at=(now - timedelta(hours=2)).isoformat(),
        modified_at=(now - timedelta(hours=2)).isoformat(),
    ))
    r3 = req_repo.create(RequestRead(
        id=0,
        requester_name="Le Van C",
        requester_email="vanc@company.com",
        project="Project Gamma",
        equipment_id="EBS-001",
        equipment_name="Sensor Temp I2C",
        quantity=1,
        needed_from="2026-12-01",
        needed_to="2026-12-05",
        purpose="Thermal sensor validation",
        priority_level="Critical",
        priority_reason="Critical safety validation",
        status="Pending",
        created_at=(now - timedelta(hours=1)).isoformat(),
        modified_at=(now - timedelta(hours=1)).isoformat(),
    ))

    conv_id = f"conv-recent-mgr-followup-{now.timestamp()}"

    # 1. 'Ai là người request gần đây nhất?' -> newest request is r3 (Le Van C)
    res1 = manager_client.post(
        "/api/agent/message",
        json={"message": "Ai là người request gần đây nhất?", "conversation_id": conv_id},
    )
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["trace"]["intent"] == "recent_request"
    assert "Le Van C" in d1["reply"]
    assert "Project Gamma" in d1["reply"]
    # Must NOT return general equipment table
    assert "Vị trí: Tủ 1" not in d1["reply"]

    # 2. 'Còn request trước đó thì sao?' -> resolves r2 (Tran Thi B)
    res2 = manager_client.post(
        "/api/agent/message",
        json={"message": "Còn request trước đó thì sao?", "conversation_id": conv_id},
    )
    assert res2.status_code == 200
    d2 = res2.json()
    assert "Tran Thi B" in d2["reply"]
    assert "Project Beta" in d2["reply"]

    # 3. 'Cho mình xem các request gần đây' -> list format
    res3 = manager_client.post(
        "/api/agent/message",
        json={"message": "Cho mình xem các request gần đây", "conversation_id": conv_id},
    )
    assert res3.status_code == 200
    d3 = res3.json()
    assert d3["trace"]["intent"] == "recent_requests"
    assert "Le Van C" in d3["reply"]
    assert "Tran Thi B" in d3["reply"]
    assert "Nguyen Van A" in d3["reply"]

    # 4. Follow-up: 'Đơn thứ 2 là ai?' -> In recent list (sorted DESC), 1st is r3, 2nd is r2 (Tran Thi B)
    res4 = manager_client.post(
        "/api/agent/message",
        json={"message": "Đơn thứ 2 là ai?", "conversation_id": conv_id},
    )
    assert res4.status_code == 200
    d4 = res4.json()
    assert "Tran Thi B" in d4["reply"]

    # 5. Follow-up: 'Cái đầu tiên của project nào?' -> 1st is r3 (Project Gamma)
    res5 = manager_client.post(
        "/api/agent/message",
        json={"message": "Cái đầu tiên của project nào?", "conversation_id": conv_id},
    )
    assert res5.status_code == 200
    d5 = res5.json()
    assert "Project Gamma" in d5["reply"]

    # 6. Follow-up: 'Đơn này mượn gì?' -> r3 borrowed Sensor Temp I2C
    res6 = manager_client.post(
        "/api/agent/message",
        json={"message": "Đơn này mượn gì?", "conversation_id": conv_id},
    )
    assert res6.status_code == 200
    d6 = res6.json()
    assert "Sensor Temp I2C" in d6["reply"] or "EBS-001" in d6["reply"]

    # 7. Follow-up: 'Đơn này ưu tiên gì?'
    res7 = manager_client.post(
        "/api/agent/message",
        json={"message": "Đơn này ưu tiên gì?", "conversation_id": conv_id},
    )
    assert res7.status_code == 200
    d7 = res7.json()
    assert "Critical" in d7["reply"]


# ---------------------------------------------------------------------------
# Sections E, F, G: Overdue loans, active loans, active borrowers
# ---------------------------------------------------------------------------

def test_overdue_and_active_loans_management(manager_client):
    """Tests overdue loan isolation vs active loans vs approved/pending loans."""
    from datetime import datetime, timezone, timedelta
    req_repo = get_request_repo()
    now = datetime.now(timezone.utc)

    # Create:
    # 1. Overdue: Status=Borrowed, NeededTo in past (2020-01-01)
    req_repo.create(RequestRead(
        id=0,
        requester_name="Overdue Borrower",
        requester_email="overdue@company.com",
        project="Legacy Project",
        equipment_id="TU1-001",
        equipment_name="Conn header SMD 24pos 3mm female",
        quantity=3,
        needed_from="2020-01-01",
        needed_to="2020-01-15",
        purpose="Past testing",
        priority_level="Low",
        priority_reason="None",
        status="Borrowed",
        created_at=(now - timedelta(days=100)).isoformat(),
        modified_at=(now - timedelta(days=100)).isoformat(),
    ))

    # 2. Active, not overdue: Status=Borrowed, NeededTo in future (2099-01-01)
    req_repo.create(RequestRead(
        id=0,
        requester_name="Active Future Borrower",
        requester_email="future@company.com",
        project="Future Project",
        equipment_id="CSW-001",
        equipment_name="Switch SPST 12V",
        quantity=2,
        needed_from="2026-01-01",
        needed_to="2026-12-31",
        purpose="Long running project",
        priority_level="Medium",
        priority_reason="Long term",
        status="Borrowed",
        created_at=now.isoformat(),
        modified_at=now.isoformat(),
    ))

    # 3. Approved (NOT yet borrowed, even if past dates) -> must NOT be counted as active loan or overdue loan
    req_repo.create(RequestRead(
        id=0,
        requester_name="Approved Only Person",
        requester_email="approved@company.com",
        project="Pending Handover Project",
        equipment_id="EBS-001",
        equipment_name="Sensor Temp I2C",
        quantity=1,
        needed_from="2020-01-01",
        needed_to="2020-01-10",
        purpose="Not yet handed over",
        priority_level="High",
        priority_reason="High",
        status="Approved",
        created_at=now.isoformat(),
        modified_at=now.isoformat(),
    ))

    conv_id = f"conv-loans-{now.timestamp()}"

    # Overdue inquiry: 'Có ai đang trả thiết bị trễ không?'
    res_overdue = manager_client.post(
        "/api/agent/message",
        json={"message": "Có ai đang trả thiết bị trễ không?", "conversation_id": conv_id},
    )
    assert res_overdue.status_code == 200
    d_overdue = res_overdue.json()
    assert d_overdue["trace"]["intent"] == "overdue_loans"
    assert "Overdue Borrower" in d_overdue["reply"]
    # Must NOT include active non-overdue or approved
    assert "Active Future Borrower" not in d_overdue["reply"]
    assert "Approved Only Person" not in d_overdue["reply"]

    # Active loans inquiry: 'Hiện tại có những thiết bị nào đang được mượn?'
    res_active = manager_client.post(
        "/api/agent/message",
        json={"message": "Hiện tại có những thiết bị nào đang được mượn?", "conversation_id": conv_id},
    )
    assert res_active.status_code == 200
    d_active = res_active.json()
    assert d_active["trace"]["intent"] == "active_loans"
    assert "Overdue Borrower" in d_active["reply"]
    assert "Active Future Borrower" in d_active["reply"]
    # Must NOT include Approved request
    assert "Approved Only Person" not in d_active["reply"]

    # Active borrowers inquiry: 'Ai đang mượn thiết bị?'
    res_borrowers = manager_client.post(
        "/api/agent/message",
        json={"message": "Ai đang mượn thiết bị?", "conversation_id": conv_id},
    )
    assert res_borrowers.status_code == 200
    d_borrowers = res_borrowers.json()
    assert d_borrowers["trace"]["intent"] == "active_borrowers"
    assert "Overdue Borrower" in d_borrowers["reply"]
    assert "Active Future Borrower" in d_borrowers["reply"]
    assert "Approved Only Person" not in d_borrowers["reply"]


# ---------------------------------------------------------------------------
# Section K: Peer manager approval (Self-approval blocked, peer manager allowed)
# ---------------------------------------------------------------------------

def test_peer_manager_can_approve_manager_request(admin_client):
    """Manager 1 cannot approve own request, but Manager 2 can approve it."""
    from datetime import datetime, timezone
    req_repo = get_request_repo()

    m1_email = "manager.alpha@company.com"
    m2_email = "manager.beta@company.com"

    admin_client.post("/api/admin/users", json={"user_email": m1_email, "user_name": "Manager 1", "role": "MANAGER"})
    admin_client.post("/api/admin/users", json={"user_email": m2_email, "user_name": "Manager 2", "role": "MANAGER"})

    client1 = TestClient(app)
    client1.post("/auth/dev-login", json={"email": m1_email})

    client2 = TestClient(app)
    client2.post("/auth/dev-login", json={"email": m2_email})

    # Manager 1 creates a request
    m1_req = req_repo.create(RequestRead(
        id=0,
        requester_name="Manager 1",
        requester_email=m1_email,
        project="Alpha Project",
        equipment_id="TU1-001",
        equipment_name="Conn header SMD 24pos 3mm female",
        quantity=1,
        needed_from="2026-12-01",
        needed_to="2026-12-02",
        purpose="M1 testing",
        priority_level="Medium",
        priority_reason="Standard",
        status="Pending",
        created_at=datetime.now(timezone.utc).isoformat(),
        modified_at=datetime.now(timezone.utc).isoformat(),
    ))

    # Manager 1 attempts to approve own request in chat -> BLOCKED
    res_self = client1.post(
        "/api/agent/message",
        json={"message": f"Duyệt đơn #{m1_req.id}", "conversation_id": f"conv-self-{m1_req.id}"},
    )
    assert res_self.status_code == 200
    assert "Không thể phê duyệt" in res_self.json()["reply"]
    assert "chính mình" in res_self.json()["reply"]

    # Manager 2 approves Manager 1's request in chat -> SUCCESS!
    res_peer = client2.post(
        "/api/agent/message",
        json={"message": f"Duyệt đơn #{m1_req.id}", "conversation_id": f"conv-peer-{m1_req.id}"},
    )
    assert res_peer.status_code == 200
    assert "Đã phê duyệt" in res_peer.json()["reply"]

    # Verify status in DB
    updated = req_repo.get_by_id(m1_req.id)
    assert updated.status == "Approved"


# ---------------------------------------------------------------------------
# Section J: Follow-up context for Manager result sets & group reference resolution
# ---------------------------------------------------------------------------

def test_manager_overdue_followup_group_reference(manager_client):
    """Regression test for Manager follow-up group reference:
    Turn 1: "Hiện có những ai đang mượn thiết bị quá hạn mà chưa trả không?"
            -> returns overdue loans.
    Turn 2: "Những người đó là ai?"
            -> resolves to overdue borrowers from previous result set WITHOUT searching equipment!
    """
    conv_id = "conv-overdue-followup-test"

    # Turn 1: Overdue loans query
    res1 = manager_client.post(
        "/api/agent/message",
        json={"message": "Hiện có những ai đang mượn thiết bị quá hạn mà chưa trả không?", "conversation_id": conv_id},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["trace"]["intent"] == "overdue_loans"
    assert "quá hạn" in data1["reply"].lower()

    # Turn 2: Follow-up group reference: "Những người đó là ai?"
    res2 = manager_client.post(
        "/api/agent/message",
        json={"message": "Những người đó là ai?", "conversation_id": conv_id},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    reply2 = data2["reply"]
    trace2 = data2["trace"]

    # Must resolve to overdue_borrowers, NOT search_equipment!
    assert trace2["intent"] == "overdue_borrowers"
    assert trace2["selected_tool"] != "search_equipment"
    assert trace2["selected_tool"] == "get_overdue_borrowers"
    assert "người dùng" in reply2.lower() or "người mượn" in reply2.lower()
    # Check that seeded borrower is present
    assert "phamngochainam25@gmail.com" in reply2 or "Phạm Ngọc Hải Nam" in reply2


def test_generic_reference_resolvers(manager_client):
    """Test generic resolvers:
    1. Ordinal request: "Đơn thứ 2"
    2. Ordinal equipment: "Cái thứ 2"
    3. Pronoun request: "Đơn này"
    4. Pronoun equipment: "Thiết bị đó"
    5. Detail expansion: "Cho mình xem chi tiết hơn"
    """
    # 1. Equipment list then "Cái thứ 2"
    conv_eq = "conv-resolver-eq"
    res_list = manager_client.post(
        "/api/agent/message",
        json={"message": "Cho mình xem danh sách connector ở Tủ 1", "conversation_id": conv_eq},
    )
    assert res_list.status_code == 200

    res_second = manager_client.post(
        "/api/agent/message",
        json={"message": "Cái thứ 2", "conversation_id": conv_eq},
    )
    assert res_second.status_code == 200
    assert res_second.json()["trace"]["intent"] == "equipment_detail"

    # Follow-up "Thiết bị đó ở đâu?"
    res_pronoun = manager_client.post(
        "/api/agent/message",
        json={"message": "Thiết bị đó", "conversation_id": conv_eq},
    )
    assert res_pronoun.status_code == 200
    assert res_pronoun.json()["trace"]["intent"] == "equipment_detail"

    # 2. Recent requests then "Đơn thứ 2"
    conv_req = "conv-resolver-req"
    res_reqs = manager_client.post(
        "/api/agent/message",
        json={"message": "Cho mình xem các request gần đây", "conversation_id": conv_req},
    )
    assert res_reqs.status_code == 200

    res_req2 = manager_client.post(
        "/api/agent/message",
        json={"message": "Đơn thứ 2", "conversation_id": conv_req},
    )
    assert res_req2.status_code == 200
    assert res_req2.json()["trace"]["intent"] == "request_detail"

    # Follow-up "Cho mình xem chi tiết hơn"
    res_detail = manager_client.post(
        "/api/agent/message",
        json={"message": "Cho mình xem chi tiết hơn", "conversation_id": conv_req},
    )
    assert res_detail.status_code == 200
    assert res_detail.json()["trace"]["intent"] == "request_detail"


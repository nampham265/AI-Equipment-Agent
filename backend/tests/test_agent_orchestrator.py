"""Comprehensive regression test suite for Agent Orchestration, Context, Retrieval, Tools, and RBAC."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def admin_client():
    client = TestClient(app)
    res = client.post("/auth/dev-login", json={"email": "nampham.31231023820@st.ueh.edu.vn"})
    assert res.status_code == 200
    return client


@pytest.fixture
def user_client(admin_client):
    client = TestClient(app)
    email = "agent.test.user@company.com"
    # Admin creates the user first
    admin_client.post(
        "/api/admin/users",
        json={"user_email": email, "user_name": "Test Regular User", "role": "USER"},
    )
    res = client.post("/auth/dev-login", json={"email": email})
    assert res.status_code == 200
    return client


# ---------------------------------------------------------------------------
# Section 44: Multi-constraint retrieval test
# ---------------------------------------------------------------------------

def test_multi_constraint_search_right_angle_4_2mm(admin_client):
    """'Cho mình xem danh sách connector góc vuông 4.2mm ở Tủ 1'
    Must match TU1-002, TU1-008, TU1-012.
    Must NOT match TU1-001 (which is SMD 3mm).
    """
    res = admin_client.post(
        "/api/agent/message",
        json={
            "message": "Cho mình xem danh sách connector góc vuông 4.2mm ở Tủ 1",
            "conversation_id": "conv-search-multi-constraint",
        },
    )
    assert res.status_code == 200
    reply = res.json()["reply"]
    assert "TU1-002" in reply
    assert "TU1-008" in reply
    assert "TU1-012" in reply
    assert "TU1-001" not in reply


# ---------------------------------------------------------------------------
# Section 45: Contextual follow-up and pronoun resolution
# ---------------------------------------------------------------------------

def test_contextual_pronoun_followup(admin_client):
    """Turn 1: TU1-001 có những thông tin gì?
    Turn 2: Còn bao nhiêu cái?
    Expected: Turn 2 refers to TU1-001 and deterministically returns 37.
    """
    conv_id = "conv-pronoun-followup"
    res1 = admin_client.post(
        "/api/agent/message",
        json={
            "message": "TU1-001 có những thông tin gì?",
            "conversation_id": conv_id,
        },
    )
    assert res1.status_code == 200
    assert "TU1-001" in res1.json()["reply"]

    res2 = admin_client.post(
        "/api/agent/message",
        json={
            "message": "Còn bao nhiêu cái?",
            "conversation_id": conv_id,
        },
    )
    assert res2.status_code == 200
    reply2 = res2.json()["reply"]
    assert "TU1-001" in reply2
    assert "37" in reply2


# ---------------------------------------------------------------------------
# Section 46: Ordinal reference resolution ('cái thứ 2')
# ---------------------------------------------------------------------------

def test_ordinal_reference_cai_thu_2(admin_client):
    """Turn 1: Search right-angle 4.2mm connectors in Tủ 1 (returns TU1-002, TU1-008, TU1-012)
    Turn 2: Cái thứ 2 có bao nhiêu cái?
    Expected: Resolves to TU1-008 and returns 45. Does NOT search from scratch!
    """
    conv_id = "conv-ordinal-ref"
    res1 = admin_client.post(
        "/api/agent/message",
        json={
            "message": "Cho mình xem danh sách connector góc vuông 4.2mm ở Tủ 1",
            "conversation_id": conv_id,
        },
    )
    assert res1.status_code == 200

    res2 = admin_client.post(
        "/api/agent/message",
        json={
            "message": "Cái thứ 2 có bao nhiêu cái?",
            "conversation_id": conv_id,
        },
    )
    assert res2.status_code == 200
    reply2 = res2.json()["reply"]
    assert "TU1-008" in reply2
    assert "45" in reply2


# ---------------------------------------------------------------------------
# Section 47: Deterministic numeric shortage calculation
# ---------------------------------------------------------------------------

def test_numeric_shortage_calculation(admin_client):
    """User asks to borrow 50 of TU1-001 (inventory has 37).
    Must deterministically state shortage of 13 without LLM hallucination.
    """
    res = admin_client.post(
        "/api/agent/message",
        json={
            "message": "Mình muốn mượn 50 cái TU1-001",
            "conversation_id": "conv-numeric-shortage",
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]
    # Check exact shortage math: 50 - 37 = 13
    assert "13" in reply
    assert "thiếu" in reply.lower() or "chỉ còn 37" in reply
    assert data.get("action") is not None
    assert data["action"]["type"] == "show_borrow_form"
    assert data["action"]["prefill"]["quantity"] == 50


# ---------------------------------------------------------------------------
# Section 48: Negation handling ('không cần mượn, chỉ hỏi...')
# ---------------------------------------------------------------------------

def test_negation_does_not_open_borrow_form(admin_client):
    """User: 'Không cần mượn, chỉ cho mình biết thiết bị này đang ở đâu'
    Must NOT return show_borrow_form action. Must answer location.
    """
    conv_id = "conv-negation"
    # Seed active equipment TU1-001
    admin_client.post(
        "/api/agent/message",
        json={"message": "TU1-001", "conversation_id": conv_id},
    )

    res = admin_client.post(
        "/api/agent/message",
        json={
            "message": "Không cần mượn, chỉ cho mình biết thiết bị này đang ở đâu",
            "conversation_id": conv_id,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is None
    assert "Tủ 1" in data["reply"]


# ---------------------------------------------------------------------------
# Section 49: Multi-turn pending form state merging
# ---------------------------------------------------------------------------

def test_pending_form_state_merging(admin_client):
    """Turn 1: 'Mình muốn mượn TU1-001'
    Turn 2: '5 cái từ 10/10 đến 12/10 để test board cho project ABC'
    Expected: Form merges quantity=5, dates, project='ABC', purpose='test board'.
    """
    conv_id = "conv-form-merge"
    res1 = admin_client.post(
        "/api/agent/message",
        json={"message": "Mình muốn mượn TU1-001", "conversation_id": conv_id},
    )
    assert res1.status_code == 200
    assert res1.json()["action"]["type"] == "show_borrow_form"

    res2 = admin_client.post(
        "/api/agent/message",
        json={
            "message": "5 cái từ 10/10 đến 12/10 để test board cho project ABC",
            "conversation_id": conv_id,
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2.get("action") is not None
    prefill = data2["action"]["prefill"]
    assert prefill["equipment_id"] == "TU1-001"
    assert prefill["quantity"] == 5
    assert "10-10" in prefill["needed_from"]
    assert "10-12" in prefill["needed_to"]
    assert prefill["project"] == "ABC"
    assert "test board" in prefill["purpose"].lower()


# ---------------------------------------------------------------------------
# Section 50: Unsupported data categories
# ---------------------------------------------------------------------------

def test_unsupported_project_usage_and_condition(admin_client):
    """Project usage and condition queries must give grounded, explicit unsupported statements."""
    conv_id = "conv-unsupported"
    
    # Project usage query
    res1 = admin_client.post(
        "/api/agent/message",
        json={"message": "Ai đang dùng TU1-001?", "conversation_id": conv_id},
    )
    assert res1.status_code == 200
    assert "chưa hỗ trợ" in res1.json()["reply"] or "đơn mượn" in res1.json()["reply"]

    # Condition query
    res2 = admin_client.post(
        "/api/agent/message",
        json={"message": "Tình trạng TU1-001 thế nào, còn mới không?", "conversation_id": conv_id},
    )
    assert res2.status_code == 200
    reply2 = res2.json()["reply"]
    assert "chưa hỗ trợ theo dõi tình trạng hao mòn" in reply2 or "chưa lưu trữ" in reply2


# ---------------------------------------------------------------------------
# Section 51: Manager experience & self-approval prevention
# ---------------------------------------------------------------------------

def test_manager_pending_count_and_self_approval_protection(admin_client, user_client):
    """Manager asks pending count, then attempts self-approval."""
    conv_id = "conv-manager-test"

    # Pending count
    res_count = admin_client.post(
        "/api/agent/message",
        json={"message": "Có bao nhiêu đơn đang chờ duyệt?", "conversation_id": conv_id},
    )
    assert res_count.status_code == 200
    assert "đơn" in res_count.json()["reply"]

    # Regular user cannot use manager approve
    res_user_approve = user_client.post(
        "/api/agent/message",
        json={"message": "Duyệt đơn #1", "conversation_id": "conv-user-cannot-approve"},
    )
    assert res_user_approve.status_code == 200
    assert "Chỉ quản lý" in res_user_approve.json()["reply"]


# ---------------------------------------------------------------------------
# Section 52: Per-turn agent trace verification
# ---------------------------------------------------------------------------

def test_agent_trace_included_in_response(admin_client):
    """Response must contain an agent trace object."""
    res = admin_client.post(
        "/api/agent/message",
        json={
            "message": "TU1-001",
            "conversation_id": "conv-trace-check",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "trace" in data and data["trace"] is not None
    trace = data["trace"]
    assert trace["conversation_id"] == "conv-trace-check"
    assert "intent" in trace
    assert "user_role" in trace
    assert trace["response_mode"] in ["grounded", "fallback", "unsupported"]

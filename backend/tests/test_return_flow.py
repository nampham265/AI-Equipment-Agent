"""Tests for Return Equipment Intent, Return Flow, and Manager Return Review."""
from __future__ import annotations

import pytest
from app.agent.models import ConversationState, IntentType
from app.agent.router import query_router
from app.schemas.requests import ReturnCondition


def test_return_intent_routing():
    """Verify return expressions route to RETURN_REQUEST, not equipment search or borrow."""
    state = ConversationState(user_email="test@example.com", conversation_id="conv-1")

    # Positive return requests
    p1 = query_router.route_message("Mình muốn trả đồ", state)
    assert p1.intent == IntentType.RETURN_REQUEST

    p2 = query_router.route_message("Tôi muốn trả lại thiết bị", state)
    assert p2.intent == IntentType.RETURN_REQUEST

    p3 = query_router.route_message("hoàn trả thiết bị", state)
    assert p3.intent == IntentType.RETURN_REQUEST

    p4 = query_router.route_message("mình muốn trả TU1-001", state)
    assert p4.intent == IntentType.RETURN_REQUEST
    assert p4.entity_id == "TU1-001"

    # Must NOT route to return_request if asking about overdue
    p_overdue1 = query_router.route_message("Có ai đang trả thiết bị trễ không?", state)
    assert p_overdue1.intent == IntentType.OVERDUE_LOANS

    p_overdue2 = query_router.route_message("Ai đang quá hạn trả thiết bị?", state)
    assert p_overdue2.intent == IntentType.OVERDUE_LOANS


def test_active_counts_intent_routing():
    """Verify distinct borrower count and active loans count routing."""
    state = ConversationState(user_email="test@example.com", conversation_id="conv-1")

    p1 = query_router.route_message("Hiện tại đang có bao nhiêu người mượn đồ?", state)
    assert p1.intent == IntentType.ACTIVE_BORROWERS_COUNT

    p2 = query_router.route_message("có mấy người mượn", state)
    assert p2.intent == IntentType.ACTIVE_BORROWERS_COUNT

    p3 = query_router.route_message("Hiện tại có bao nhiêu thiết bị đang được mượn?", state)
    assert p3.intent == IntentType.ACTIVE_LOANS_COUNT

    p4 = query_router.route_message("bao nhiêu thiết bị đang mượn", state)
    assert p4.intent == IntentType.ACTIVE_LOANS_COUNT


def test_allowed_return_conditions():
    """Verify the 6 allowed ReturnCondition values match specification."""
    expected = [
        "Nguyên trạng như khi nhận",
        "Có hao mòn nhẹ, vẫn sử dụng bình thường",
        "Hư hỏng nhẹ",
        "Hư hỏng nặng",
        "Hư hỏng nhưng đã khắc phục",
        "Cần kiểm tra thêm",
    ]
    for val in expected:
        assert ReturnCondition(val).value == val


@pytest.fixture
def admin_client():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    res = client.post("/auth/dev-login", json={"email": "nampham.31231023820@st.ueh.edu.vn"})
    assert res.status_code == 200
    return client


@pytest.fixture
def user_client(admin_client):
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    email = "return.test.user@company.com"
    admin_client.post(
        "/api/admin/users",
        json={"user_email": email, "user_name": "Test Return User", "role": "USER"},
    )
    res = client.post("/auth/dev-login", json={"email": email})
    assert res.status_code == 200
    return client


def test_return_flow_no_active_loans(user_client):
    """User with no active loans asks to return equipment -> explains no loans, no form."""
    res = user_client.post(
        "/api/agent/message",
        json={"message": "Mình muốn trả đồ", "conversation_id": "conv-return-no-loans"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is None
    assert "chưa ghi nhận" in data["reply"]


def test_active_borrowers_count_chat(admin_client):
    """Manager asks 'Hiện tại đang có bao nhiêu người mượn đồ?' -> returns counts, no borrow form."""
    res = admin_client.post(
        "/api/agent/message",
        json={"message": "Hiện tại đang có bao nhiêu người mượn đồ?", "conversation_id": "conv-borrowers-cnt"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is None
    assert "người đang mượn" in data["reply"] or "không có người nào" in data["reply"]


def test_manager_conflicts_endpoint(admin_client):
    """Manager calls /api/manager/conflicts -> returns list of conflicts."""
    res = admin_client.get("/api/manager/conflicts")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_manager_returns_review_endpoint(admin_client):
    """Manager calls /api/manager/returns-review -> returns list of returns needing attention."""
    res = admin_client.get("/api/manager/returns-review")
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    # Check that any items returned have one of the attention conditions
    for it in items:
        assert it["return_condition"] in ["Hư hỏng nhẹ", "Hư hỏng nặng", "Cần kiểm tra thêm"]

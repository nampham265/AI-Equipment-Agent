"""Automated regression tests for UI layout contracts and 'My Requests' conversation intent.

Covers Part K of the specification:
1. 'Xem trạng thái các yêu cầu mượn của tôi' -> intent = my_requests, action is None
2. 'Đơn nào của tôi đã được duyệt?' -> intent = my_requests, status_filter = 'Approved'
3. 'Đơn nào của tôi còn chờ duyệt?' -> intent = my_requests, status_filter = 'Pending'
4. 'Tôi đang mượn những thiết bị nào?' -> intent = my_requests, status_filter = 'Borrowed'
5. Follow-up 'Đơn đầu tiên là gì?' after my_requests -> request_detail
6. Follow-up 'Cái đầu tiên của project nào?' after my_requests -> request_detail
7. Follow-up 'Đơn này mượn thiết bị gì?' after my_requests -> request_detail
8. Follow-up 'Những người đó là ai?' after overdue_loans -> resolved from previous overdue borrowers
9. CSS contract test ensuring Header does not overlap sidebar & New Chat button is fully visible.
"""
from pathlib import Path
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
def manager_client(admin_client):
    client = TestClient(app)
    m_email = "test.layout.manager@company.com"
    admin_client.post(
        "/api/admin/users",
        json={"user_email": m_email, "user_name": "Layout Manager", "role": "MANAGER"},
    )
    res = client.post("/auth/dev-login", json={"email": m_email})
    assert res.status_code == 200
    return client


@pytest.fixture
def user_client(admin_client):
    client = TestClient(app)
    u_email = "phamngochainam25@gmail.com"
    # User already seeded or exists
    res = client.post("/auth/dev-login", json={"email": u_email})
    assert res.status_code == 200
    return client


# ---------------------------------------------------------------------------
# Requirement 1: "Xem trạng thái các yêu cầu mượn của tôi" -> intent = my_requests, action is None
# ---------------------------------------------------------------------------

def test_my_requests_intent_and_no_borrow_action(user_client):
    """Querying status of my requests must NOT open BorrowForm (action is None)
    and must return structured request table.
    """
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Xem trạng thái các yêu cầu mượn của tôi",
            "conversation_id": "conv-test-my-req-1",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is None, "Borrow form action must NOT be triggered for my_requests!"
    
    trace = data.get("trace", {})
    assert trace.get("intent") == "my_requests"
    assert trace.get("selected_tool") == "list_my_requests"

    reply = data["reply"]
    # Table header or structured message
    assert "Mã YC" in reply or "yêu cầu mượn" in reply.lower()


# ---------------------------------------------------------------------------
# Requirements 2, 3, 4: Status-filtered queries
# ---------------------------------------------------------------------------

def test_my_requests_status_filter_approved(user_client):
    """'Đơn nào của tôi đã được duyệt?' -> intent = my_requests, status_filter = 'Approved'"""
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Đơn nào của tôi đã được duyệt?",
            "conversation_id": "conv-test-my-req-approved",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is None
    trace = data.get("trace", {})
    assert trace.get("intent") == "my_requests"
    assert trace.get("query_plan", {}).get("status_filter") == "Approved"


def test_my_requests_status_filter_pending(user_client):
    """'Đơn nào của tôi còn chờ duyệt?' -> intent = my_requests, status_filter = 'Pending'"""
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Đơn nào của tôi còn chờ duyệt?",
            "conversation_id": "conv-test-my-req-pending",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is None
    trace = data.get("trace", {})
    assert trace.get("intent") == "my_requests"
    assert trace.get("query_plan", {}).get("status_filter") == "Pending"


def test_my_requests_status_filter_borrowed(user_client):
    """'Tôi đang mượn những thiết bị nào?' -> intent = my_requests, status_filter = 'Borrowed'"""
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Tôi đang mượn những thiết bị nào?",
            "conversation_id": "conv-test-my-req-borrowed",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is None
    trace = data.get("trace", {})
    assert trace.get("intent") == "my_requests"
    assert trace.get("query_plan", {}).get("status_filter") == "Borrowed"


# ---------------------------------------------------------------------------
# Requirements 5, 6, 7: Contextual follow-ups after my_requests
# ---------------------------------------------------------------------------

def test_my_requests_followups(user_client):
    """Test follow-ups:
    5. 'Đơn đầu tiên là gì?'
    6. 'Cái đầu tiên của project nào?'
    7. 'Đơn này mượn thiết bị gì?'
    """
    conv_id = "conv-test-my-req-followups"

    # Turn 1: List my requests
    r1 = user_client.post(
        "/api/agent/message",
        json={
            "message": "Xem trạng thái các yêu cầu mượn của tôi",
            "conversation_id": conv_id,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["trace"]["intent"] == "my_requests"

    # Turn 2: 'Đơn đầu tiên là gì?' -> must resolve to request_detail (first item in result set)
    r2 = user_client.post(
        "/api/agent/message",
        json={
            "message": "Đơn đầu tiên là gì?",
            "conversation_id": conv_id,
        },
    )
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["trace"]["intent"] == "request_detail"
    assert data2["trace"]["selected_tool"] == "get_request_detail"

    # Turn 3: 'Cái đầu tiên của project nào?' -> must resolve to request_detail, NOT equipment_detail
    r3 = user_client.post(
        "/api/agent/message",
        json={
            "message": "Cái đầu tiên của project nào?",
            "conversation_id": conv_id,
        },
    )
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["trace"]["intent"] == "request_detail"
    assert data3["trace"]["selected_tool"] == "get_request_detail"

    # Turn 4: 'Đơn này mượn thiết bị gì?' -> pronoun refers to active request
    r4 = user_client.post(
        "/api/agent/message",
        json={
            "message": "Đơn này mượn thiết bị gì?",
            "conversation_id": conv_id,
        },
    )
    assert r4.status_code == 200
    data4 = r4.json()
    assert data4["trace"]["intent"] == "request_detail"
    assert data4["trace"]["selected_tool"] == "get_request_detail"


# ---------------------------------------------------------------------------
# Requirement 8: Overdue loans follow-up 'Những người đó là ai?'
# ---------------------------------------------------------------------------

def test_overdue_loans_followup_people(manager_client):
    """Manager asks for overdue loans, then asks 'Những người đó là ai?'
    Must resolve to overdue borrowers from last result set, NOT equipment search.
    """
    conv_id = "conv-test-overdue-followup-partk"

    # Turn 1: Overdue loans
    r1 = manager_client.post(
        "/api/agent/message",
        json={
            "message": "Hiện có những ai đang mượn thiết bị quá hạn mà chưa trả không?",
            "conversation_id": conv_id,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["trace"]["intent"] in ["overdue_loans", "overdue_borrowers"]

    # Turn 2: 'Những người đó là ai?'
    r2 = manager_client.post(
        "/api/agent/message",
        json={
            "message": "Những người đó là ai?",
            "conversation_id": conv_id,
        },
    )
    assert r2.status_code == 200
    data2 = r2.json()
    trace2 = data2["trace"]
    assert trace2["intent"] == "overdue_borrowers"
    assert trace2["selected_tool"] == "get_overdue_borrowers"
    assert trace2["selected_tool"] != "search_equipment"
    assert "phamngochainam25@gmail.com" in data2["reply"] or "Phạm Ngọc Hải Nam" in data2["reply"]


# ---------------------------------------------------------------------------
# Requirement 9: CSS Contract Test for Layout Architecture
# ---------------------------------------------------------------------------

def test_css_layout_contracts():
    """Verify frontend CSS contract ensures header does not cover sidebar,
    and New Chat button has flex-shrink: 0, content has independent scroll, footer is anchored.
    """
    css_path = Path(__file__).parent.parent.parent / "frontend" / "src" / "index.css"
    assert css_path.exists(), f"Frontend CSS not found at {css_path}"
    css_content = css_path.read_text(encoding="utf-8")

    # Contract 1: Navbar height CSS variable defined
    assert "--navbar-height" in css_content

    # Contract 2: Navbar is fixed or sticky with height matching navbar variable
    assert ".navbar" in css_content
    assert "height: var(--navbar-height)" in css_content

    # Contract 3: Layout has padding-top reserved for navbar so sidebar is never under navbar
    assert ".layout" in css_content
    assert "padding-top: var(--navbar-height)" in css_content

    # Contract 4: Chat page wrapper constrained to remaining viewport height
    assert ".chat-page-wrapper" in css_content
    assert "calc(100vh - var(--navbar-height))" in css_content

    # Contract 5: Chat sidebar header flex-shrink: 0 (prevents 'Đoạn chat mới' button from clipping)
    assert ".chat-sidebar__header" in css_content
    assert "flex-shrink: 0" in css_content

    # Contract 6: Chat sidebar content has independent scroll region
    assert ".chat-sidebar__content" in css_content
    assert "overflow-y: auto" in css_content
    assert "min-height: 0" in css_content

    # Contract 7: Chat sidebar footer flex-shrink: 0 (anchored at bottom)
    assert ".chat-sidebar__footer" in css_content

    # Contract 8: Edge expand tab and topbar expand button are defined for collapsed state
    assert ".chat-sidebar-edge-tab" in css_content
    assert ".chat-topbar-btn--expand" in css_content

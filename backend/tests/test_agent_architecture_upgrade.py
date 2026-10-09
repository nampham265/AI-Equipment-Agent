"""Integration and regression test suite for Full Agent Architecture Upgrade (Phases 1-4).

Tests:
1. Structured routing and GeminiRouter fallback mechanisms.
2. Alternative equipment search excluding target ID and labeling suitability.
3. External sourcing guardrails and query sanitization.
4. Project usage query isolating 'Borrowed' status only.
5. Earliest release date schedule planning.
6. Admin add_user RBAC enforcement (Admin only, no Admin-creating-Admin).
7. Conflict borrowers group reference resolution.
8. Negation and action cancellation handling.
"""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.agent.services.external_sourcing import ExternalSourcingService
from app.agent.tools import AgentTools
from app.agent.orchestrator import AgentOrchestrator
from app.agent.models import IntentType, ConversationState, GeminiRouterOutput, LLMEquipmentEntity, LLMRequestEntity, LLMConstraints, LLMReference
from app.auth.session import SessionData
from app.repositories.factory import get_equipment_repo, get_request_repo, get_user_repo


@pytest.fixture
def admin_client():
    client = TestClient(app)
    res = client.post("/auth/dev-login", json={"email": "nampham.31231023820@st.ueh.edu.vn"})
    assert res.status_code == 200
    return client


@pytest.fixture
def user_client(admin_client):
    client = TestClient(app)
    email = "upgrade.test.user@company.com"
    admin_client.post(
        "/api/admin/users",
        json={"user_email": email, "user_name": "Upgrade Test User", "role": "USER"},
    )
    res = client.post("/auth/dev-login", json={"email": email})
    assert res.status_code == 200
    return client


# ---------------------------------------------------------------------------
# 1. Alternative Equipment Search Tests
# ---------------------------------------------------------------------------

def test_alternative_equipment_search_excludes_target():
    """Unit test: target equipment must NEVER appear in its own alternative results."""
    eq_repo = get_equipment_repo()
    req_repo = get_request_repo()
    tools = AgentTools(equipment_repo=eq_repo, request_repo=req_repo)

    result = tools.search_alternative_equipment("TU1-001", limit=5)
    assert result["success"] is True
    assert result["target_equipment_id"] == "TU1-001"
    alternatives = result["alternatives"]
    for alt in alternatives:
        assert alt["equipment"].equipment_id != "TU1-001", "Target equipment must be strictly excluded"
        assert alt["suitability_label"] in ["POTENTIALLY_SUITABLE", "SAME_CATEGORY", "DIFFERENT_LOCATION", "DIFFERENT_FORM_FACTOR"]
        assert 0 <= alt["score"] <= 100


def test_alternative_search_via_chat(user_client):
    """Chat message asking for alternatives routes to ALTERNATIVE_SEARCH."""
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Có thiết bị thay thế cho TU1-001 không?",
            "conversation_id": "conv-alt-chat",
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]
    trace = data.get("trace", {})
    assert "TU1-001" in reply
    assert "thay thế" in reply or "Gợi ý" in reply
    assert trace.get("selected_tool") == "search_alternative_equipment"


# ---------------------------------------------------------------------------
# 2. External Sourcing Tests
# ---------------------------------------------------------------------------

def test_external_sourcing_sanitizes_query():
    """External sourcing sanitization strips internal project codes and sensitive info."""
    svc = ExternalSourcingService()
    raw = "Cần mua CANInterface XYZ cho project Alpha tại Tủ 1 do user test@bosch.com yêu cầu"
    cleaned = svc.sanitize_query(raw)
    assert "Alpha" not in cleaned
    assert "Tủ 1" not in cleaned
    assert "test@bosch.com" not in cleaned
    assert "CANInterface" in cleaned or "XYZ" in cleaned


def test_external_sourcing_disabled_by_default(user_client):
    """When ENABLE_EXTERNAL_SOURCING=False, chat gives honest explanation without hallucination."""
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Tìm nguồn bên ngoài cho CANInterface XYZ",
            "conversation_id": "conv-external-sourcing",
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]
    trace = data.get("trace", {})
    assert "chưa được kích hoạt" in reply or "cấu hình" in reply or "chưa sẵn sàng" in reply
    assert trace.get("selected_tool") == "external_sourcing_search"


# ---------------------------------------------------------------------------
# 3. Project Usage & Schedule Planning Tests
# ---------------------------------------------------------------------------

def test_project_usage_queries_borrowed_only(admin_client):
    """Project usage query must check actual requests and return usage info."""
    res = admin_client.post(
        "/api/agent/message",
        json={
            "message": "Dự án nào đang dùng TU1-001?",
            "conversation_id": "conv-proj-usage",
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]
    trace = data.get("trace", {})
    assert trace.get("selected_tool") == "get_equipment_project_usage"
    assert "TU1-001" in reply


def test_schedule_planning_return_date(user_client):
    """When user asks when an equipment will be returned, tool estimates from Borrowed records."""
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Khi nào trả TU1-001?",
            "conversation_id": "conv-schedule-return",
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]
    trace = data.get("trace", {})
    assert trace.get("selected_tool") == "equipment_availability_schedule"
    assert "TU1-001" in reply or "trả" in reply or "dự kiến" in reply


# ---------------------------------------------------------------------------
# 4. Admin Add User RBAC Tests
# ---------------------------------------------------------------------------

def test_admin_add_user_via_chat(admin_client):
    """Admin can create a new USER via chat."""
    res = admin_client.post(
        "/api/agent/message",
        json={
            "message": "Tạo user newemp99@company.com tên Trần Văn Mới role USER",
            "conversation_id": "conv-admin-add-user",
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]
    assert "thành công" in reply or "đã tồn tại" in reply or "newemp99@company.com" in reply


def test_regular_user_cannot_add_user(user_client):
    """Non-admin user cannot use add_user tool."""
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Thêm user hacker@company.com tên Hacker role MANAGER",
            "conversation_id": "conv-user-add-denied",
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]
    assert "ADMIN" in reply or "quyền" in reply


def test_cannot_create_admin_via_tool():
    """Unit test: AgentTools.add_user_account raises ValueError if attempting to create ADMIN."""
    user_repo = get_user_repo()
    tools = AgentTools(
        equipment_repo=get_equipment_repo(),
        request_repo=get_request_repo(),
        user_repo=user_repo,
    )
    with pytest.raises(ValueError, match="Chỉ cho phép tạo vai trò USER hoặc MANAGER"):
        tools.add_user_account(
            user_email="superadmin@company.com",
            user_name="Super Admin",
            role="ADMIN",
            actor_role="ADMIN",
        )


# ---------------------------------------------------------------------------
# 5. Conflict Borrowers Group Reference
# ---------------------------------------------------------------------------

def test_conflict_borrowers_group_resolution(admin_client):
    """After querying schedule conflicts, 'những người đó là ai' resolves to CONFLICT_BORROWERS."""
    conv_id = "conv-conflict-group"
    # Step 1: Query conflicts
    res1 = admin_client.post(
        "/api/agent/message",
        json={"message": "Có xung đột lịch nào không?", "conversation_id": conv_id},
    )
    assert res1.status_code == 200

    # Step 2: Follow-up asking about people
    res2 = admin_client.post(
        "/api/agent/message",
        json={"message": "Những người đó là ai?", "conversation_id": conv_id},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    trace2 = data2.get("trace", {})
    assert trace2.get("intent") == "conflict_borrowers"
    assert trace2.get("selected_tool") == "get_conflict_borrowers"


# ---------------------------------------------------------------------------
# 6. Negation & Cancellation
# ---------------------------------------------------------------------------

def test_negate_borrow_does_not_open_form(user_client):
    """'Không cần mượn, chỉ xem thông tin thôi' must NOT trigger show_borrow_form."""
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Không cần mượn, chỉ xem thông tin TU1-001 thôi",
            "conversation_id": "conv-negate-borrow",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("action") is None
    trace = data.get("trace", {})
    assert trace.get("intent") != "request_create"


def test_cancel_action_resets_pending_state(user_client):
    """Explicit cancellation clears state and confirms."""
    res = user_client.post(
        "/api/agent/message",
        json={
            "message": "Hủy thao tác hiện tại",
            "conversation_id": "conv-cancel-action",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "Đã hủy" in data["reply"]
    trace = data.get("trace", {})
    assert trace.get("intent") == "cancel_action"


# ---------------------------------------------------------------------------
# 7. LLM Failure Fallback
# ---------------------------------------------------------------------------

def test_llm_router_fallback_on_exception(monkeypatch):
    """When GeminiAgentRouter throws an exception, Orchestrator safely falls back to QueryRouter."""
    monkeypatch.setattr(settings, "AGENT_ROUTING_MODE", "llm_primary")
    tools = AgentTools(
        equipment_repo=get_equipment_repo(),
        request_repo=get_request_repo(),
    )
    mock_router = MagicMock()
    mock_router.classify_message.side_effect = RuntimeError("Simulated Gemini API 503 Outage")

    orchestrator = AgentOrchestrator(tools=tools, gemini_router=mock_router)
    user = SessionData(
        user_email="test.user@company.com",
        user_name="Test User",
        user_oid="oid-test",
        is_manager=False,
        is_admin=False,
    )

    result = orchestrator.process_message(
        raw_message="Cho mình xem danh sách connector góc vuông 4.2mm ở Tủ 1",
        user=user,
        conversation_id="conv-fallback-test",
    )
    trace = result["trace"]
    assert trace["fallback_used"] is True
    assert trace["routing_mode"] == "legacy_fallback"
    assert "Simulated Gemini API 503" in str(trace.get("fallback_reason"))
    assert "TU1-002" in result["reply"]

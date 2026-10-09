"""Mandatory Automated Regression Tests for Hotfix & UX Repair (Phases A through E)."""
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from datetime import datetime, timezone

from app.agent.models import (
    ConversationState,
    ExtractedConstraints,
    GeminiRouterOutput,
    IntentType,
    QueryPlan,
)
from app.agent.normalizer import check_ask_auto_approve, check_existence_query
from app.agent.orchestrator import AgentOrchestrator, _map_gemini_to_plan
from app.agent.router import query_router
from app.agent.state import state_manager
from app.agent.tools import AgentTools
from app.auth.session import SessionData
from app.repositories.factory import get_equipment_repo, get_request_repo, get_user_repo
from app.schemas.requests import RequestRead, RequestStatus
from app.services.approval_service import ApprovalService
from app.services.notification_service import NotificationService


@pytest.fixture
def test_user():
    return SessionData(
        user_email="phamngochainam25@gmail.com",
        user_name="Nam Pham",
        user_oid="oid-nam",
        is_manager=False,
    )


@pytest.fixture
def other_user():
    return SessionData(
        user_email="other_user@company.com",
        user_name="Other User",
        user_oid="oid-other",
        is_manager=False,
    )


@pytest.fixture
def orchestrator():
    eq_repo = get_equipment_repo()
    req_repo = get_request_repo()
    user_repo = get_user_repo()
    tools = AgentTools(eq_repo, req_repo, user_repo)
    return AgentOrchestrator(tools=tools, gemini_router=None)


# =====================================================================
# A. Gemini Routing Tests (A1 - A5)
# =====================================================================

def test_a1_valid_gemini_classification_mapped_without_name_error(test_user):
    """Test A1: A valid Gemini classification is accepted and mapped without NameError."""
    gemini_out = GeminiRouterOutput(
        intent=IntentType.EQUIPMENT_COUNT,
        confidence=0.98,
        equipment={"equipment_id": "TU1-001", "equipment_name": "Conn header SMD"},
        request={"quantity": 10},
    )
    state = ConversationState(conversation_id="conv_a1", user_email=test_user.user_email)
    raw_msg = "Kho có bao nhiêu cái TU1-001?"
    
    plan = _map_gemini_to_plan(gemini_out, raw_msg, state)
    assert plan.intent == IntentType.EQUIPMENT_COUNT
    assert plan.entity_id == "TU1-001"
    assert plan.ask_auto_approve is False


def test_a2_successful_gemini_call_does_not_trigger_fallback(test_user, monkeypatch):
    """Test A2: A successful Gemini call uses llm_primary and does not trigger fallback."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "AGENT_ROUTING_MODE", "llm_primary")

    eq_repo = get_equipment_repo()
    req_repo = get_request_repo()
    user_repo = get_user_repo()
    tools = AgentTools(eq_repo, req_repo, user_repo)

    mock_gemini = MagicMock()
    mock_gemini.classify_message.return_value = GeminiRouterOutput(
        intent=IntentType.EQUIPMENT_COUNT,
        confidence=0.99,
        equipment={"equipment_id": "TU1-001", "equipment_name": "Conn header SMD"},
    )

    orch = AgentOrchestrator(tools=tools, gemini_router=mock_gemini)
    res = orch.process_message("Kho có bao nhiêu cái TU1-001?", test_user, "conv_a2")

    assert res["trace"]["routing_mode"] == "llm_primary"
    assert res["trace"]["llm_router_called"] is True
    assert res["trace"]["fallback_used"] is False
    assert res["trace"]["fallback_reason"] is None


def test_a3_real_gemini_api_failure_triggers_fallback(test_user, monkeypatch):
    """Test A3: A real Gemini API failure triggers fallback gracefully."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "AGENT_ROUTING_MODE", "llm_primary")

    eq_repo = get_equipment_repo()
    req_repo = get_request_repo()
    user_repo = get_user_repo()
    tools = AgentTools(eq_repo, req_repo, user_repo)

    mock_gemini = MagicMock()
    mock_gemini.classify_message.side_effect = RuntimeError("503 Service Unavailable: High load")

    orch = AgentOrchestrator(tools=tools, gemini_router=mock_gemini)
    res = orch.process_message("Kho có bao nhiêu cái TU1-001?", test_user, "conv_a3")

    assert res["trace"]["routing_mode"] == "legacy_fallback"
    assert res["trace"]["llm_router_called"] is True
    assert res["trace"]["fallback_used"] is True
    assert "503 Service Unavailable" in res["trace"]["fallback_reason"]
    # Fallback to query_router still resolved intent correctly
    assert res["trace"]["intent"] == "equipment_count"


def test_a4_invalid_json_or_intent_triggers_controlled_fallback(test_user, monkeypatch):
    """Test A4: None output or unmapped intent triggers controlled fallback."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "AGENT_ROUTING_MODE", "llm_primary")

    eq_repo = get_equipment_repo()
    req_repo = get_request_repo()
    user_repo = get_user_repo()
    tools = AgentTools(eq_repo, req_repo, user_repo)

    mock_gemini = MagicMock()
    mock_gemini.classify_message.return_value = None

    orch = AgentOrchestrator(tools=tools, gemini_router=mock_gemini)
    res = orch.process_message("Kho có bao nhiêu cái TU1-001?", test_user, "conv_a4")

    assert res["trace"]["routing_mode"] == "legacy_fallback"
    assert res["trace"]["fallback_used"] is True
    assert res["trace"]["intent"] == "equipment_count"


def test_a5_auto_approval_detector_cannot_bypass_approval_policy(test_user):
    """Test A5: Auto-approval detector detects attempt and ensures no auto-approval occurs."""
    msg = "Mình muốn mượn TU1-001, bạn duyệt luôn hộ mình nhé"
    assert check_ask_auto_approve(msg) is True

    eq_repo = get_equipment_repo()
    req_repo = get_request_repo()
    user_repo = get_user_repo()
    tools = AgentTools(eq_repo, req_repo, user_repo)
    orch = AgentOrchestrator(tools=tools, gemini_router=None)

    res = orch.process_message(msg, test_user, "conv_a5")
    # Must warn the user that AI cannot auto-approve
    assert "không có quyền tự phê duyệt" in res["reply"]
    # Form action opened without Approved status
    assert res.get("action", {}).get("type") == "show_borrow_form"


# =====================================================================
# B. Inventory Search Tests (B1 - B6)
# =====================================================================

def test_b1_inventory_search_nhung_mon_gi(orchestrator, test_user):
    """Test B1: 'Hiện tại trong kho đang có những món gì' lists inventory."""
    res = orchestrator.process_message("Hiện tại trong kho đang có những món gì", test_user, "conv_b1")
    assert "Danh sách thiết bị trong hệ thống" in res["reply"]
    assert "TU1-001" in res["reply"]
    assert res.get("action") is None


def test_b2_inventory_search_nhung_thiet_bi_gi(orchestrator, test_user):
    """Test B2: 'Hiện tại trong kho đang có những thiết bị gì' lists inventory."""
    res = orchestrator.process_message("Hiện tại trong kho đang có những thiết bị gì", test_user, "conv_b2")
    assert "Danh sách thiết bị trong hệ thống" in res["reply"]
    assert "TU1-001" in res["reply"]
    assert res.get("action") is None


def test_b3_inventory_search_loai_thiet_bi_nao(orchestrator, test_user):
    """Test B3: 'Trong kho hiện có những loại thiết bị nào?' lists inventory."""
    res = orchestrator.process_message("Trong kho hiện có những loại thiết bị nào?", test_user, "conv_b3")
    assert "Danh sách thiết bị trong hệ thống" in res["reply"]
    assert "TU1-001" in res["reply"]
    assert res.get("action") is None


def test_b4_multi_constraint_quantity_query(orchestrator, test_user):
    """Test B4: 'connector góc vuông 4.2mm ở Tủ 1 còn bao nhiêu' returns matching records' quantities."""
    res = orchestrator.process_message("connector góc vuông 4.2mm ở Tủ 1 còn bao nhiêu", test_user, "conv_b4")
    assert "Tìm thấy" in res["reply"]
    assert "TU1-002" in res["reply"]
    assert "TU1-008" in res["reply"]
    assert "TU1-012" in res["reply"]
    assert "Khả dụng" in res["reply"]


def test_b5_existing_exact_id_lookup_works(orchestrator, test_user):
    """Test B5: An existing exact-ID lookup still works."""
    res = orchestrator.process_message("Cho mình xem thông tin TU1-001", test_user, "conv_b5")
    assert "Thông tin thiết bị" in res["reply"]
    assert "TU1-001" in res["reply"]
    assert res.get("action") is None


def test_b6_separate_equipment_phrase_and_project(test_user):
    """Test B6: 'Mình cần CANInterface XYZ cho project Alpha' separates equipment and project."""
    state = ConversationState(conversation_id="conv_b6", user_email=test_user.user_email)
    msg = "Mình cần CANInterface XYZ cho project Alpha"
    plan = query_router.route_message(msg, state)
    assert plan.project == "Alpha"
    assert "alpha" not in [k.lower() for k in plan.constraints.keywords]
    assert "caninterface" in [k.lower() for k in plan.constraints.keywords]


# =====================================================================
# C. Borrow Flow Tests (C1 - C4)
# =====================================================================

def test_c1_borrow_precheck_abs(orchestrator, test_user):
    """Test C1: 'Mình muốn mượn cục ABS' searches inventory, presents candidates, then ordinal selects."""
    # Turn 1
    r1 = orchestrator.process_message("Mình muốn mượn cục ABS", test_user, "conv_c1")
    assert "tìm thấy" in r1["reply"].lower()
    assert "CSW-001" in r1["reply"]
    assert r1.get("action") is None

    # State has pending_action = borrow_select
    st = state_manager.get_state(test_user.user_email, "conv_c1")
    assert st.pending_action == "borrow_select"

    # Turn 2: Followup ordinal selection
    r2 = orchestrator.process_message("cái thứ 1", test_user, "conv_c1")
    assert r2.get("action") is not None
    assert r2["action"]["type"] == "show_borrow_form"
    assert r2["action"]["prefill"]["equipment_id"] == "CSW-001"
    assert r2["action"]["prefill"]["project"] == ""


def test_c2_borrow_field_preservation(orchestrator, test_user):
    """Test C2: 'Mình muốn mượn 5 cái TU1-001 cho project Alpha để test board' preserves all fields."""
    msg = "Mình muốn mượn 5 cái TU1-001 cho project Alpha để test board"
    res = orchestrator.process_message(msg, test_user, "conv_c2")
    act = res.get("action")
    assert act is not None
    assert act["type"] == "show_borrow_form"
    assert act["prefill"]["equipment_id"] == "TU1-001"
    assert act["prefill"]["quantity"] == 5
    assert act["prefill"]["project"] == "Alpha"
    assert "test board" in act["prefill"]["purpose"]


def test_c3_missing_project_not_silently_filled_with_minilab(orchestrator, test_user):
    """Test C3: A missing required project is left empty, never filled with Minilab."""
    res = orchestrator.process_message("Mình muốn mượn TU1-001", test_user, "conv_c3")
    act = res.get("action")
    assert act is not None
    assert act["prefill"]["project"] == ""
    assert act["prefill"]["project"] != "Minilab"


def test_c4_no_automatic_approval_occurs(test_user):
    """Test C4: Creating a borrow request via tools sets Status='Pending', not 'Approved'."""
    eq_repo = get_equipment_repo()
    req_repo = get_request_repo()
    user_repo = get_user_repo()
    tools = AgentTools(eq_repo, req_repo, user_repo)

    req = tools.create_request(
        requester_name=test_user.user_name,
        requester_email=test_user.user_email,
        project="Test Project",
        equipment_id="TU1-001",
        quantity=1,
        needed_from="2026-11-01",
        needed_to="2026-11-10",
        purpose="Testing regression C4",
    )
    assert req.status == "Pending"
    assert req.status != "Approved"


# =====================================================================
# D. Return Flow Tests (D1 - D8)
# =====================================================================

def test_d1_return_intent_lists_eligible_loans(orchestrator, test_user):
    """Test D1: 'Mình muốn trả đồ' lists eligible borrowed requests."""
    res = orchestrator.process_message("Mình muốn trả đồ", test_user, "conv_d1")
    assert "yêu cầu mượn đang hoạt động" in res["reply"]
    st = state_manager.get_state(test_user.user_email, "conv_d1")
    assert st.pending_action == "return"
    assert st.last_result_type == "borrowed_loans"


def test_d2_ordinal_selection_opens_return_form(orchestrator, test_user):
    """Test D2: Previous list -> 'Tôi muốn trả cái thứ 1' opens ReturnForm for loan #1."""
    orchestrator.process_message("Mình muốn trả đồ", test_user, "conv_d2")
    res2 = orchestrator.process_message("Tôi muốn trả cái thứ 1", test_user, "conv_d2")

    assert res2.get("action") is not None
    assert res2["action"]["type"] == "show_return_form"
    assert res2["action"]["prefill"]["equipment_id"] == "TU1-001"
    assert res2["action"]["prefill"]["request_id"] == 71


def test_d3_name_based_resolution_conn_4_2mm(orchestrator, test_user):
    """Test D3: 'Mình muốn trả Conn 4.2mm' resolves active loan TU1-008."""
    res = orchestrator.process_message("Mình muốn trả Conn 4.2mm", test_user, "conv_d3")
    assert res.get("action") is not None
    assert res["action"]["type"] == "show_return_form"
    assert res["action"]["prefill"]["equipment_id"] == "TU1-008"
    assert res["action"]["prefill"]["request_id"] == 72


def test_d4_and_d5_submitting_return_updates_request_and_removes_from_active(test_user):
    """Test D4 & D5: Submitting return updates request to Returned and removes it from active loans."""
    req_repo = get_request_repo()
    eq_repo = get_equipment_repo()
    approval_svc = ApprovalService(req_repo, NotificationService(None))

    # Create a temporary borrowed request
    temp_req = req_repo.create(RequestRead(
        id=0,
        requester_name=test_user.user_name,
        requester_email=test_user.user_email,
        project="Regression D4",
        equipment_id="TU1-003",
        equipment_name="Test Item D4",
        quantity=1,
        needed_from="2026-01-01",
        needed_to="2026-01-10",
        purpose="Regression test",
        priority_level="Needs review",
        priority_reason="Test reason",
        status="Borrowed",
        created_at=datetime.now(timezone.utc).isoformat(),
        modified_at=datetime.now(timezone.utc).isoformat(),
    ))

    # Verify it is in active loans
    tools = AgentTools(eq_repo, req_repo)
    active = tools.get_active_loans_for_user(test_user.user_email)
    assert any(r.id == temp_req.id for r in active)

    # Submit return
    returned_req = approval_svc.mark_returned(
        request_id=temp_req.id,
        return_condition="Tốt",
        return_condition_note="Kiểm tra D4",
        actor_email=test_user.user_email,
    )
    assert returned_req.status == "Returned"

    # D5: Must not appear in active loans anymore
    active_after = tools.get_active_loans_for_user(test_user.user_email)
    assert not any(r.id == temp_req.id for r in active_after)


def test_d6_returning_ineligible_request_rejected(test_user):
    """Test D6: Returning a Pending request is rejected with HTTPException 400."""
    req_repo = get_request_repo()
    approval_svc = ApprovalService(req_repo, NotificationService(None))

    pending_req = req_repo.create(RequestRead(
        id=0,
        requester_name=test_user.user_name,
        requester_email=test_user.user_email,
        project="Regression D6",
        equipment_id="TU1-003",
        equipment_name="Test Item D6",
        quantity=1,
        needed_from="2026-01-01",
        needed_to="2026-01-10",
        purpose="Regression test",
        priority_level="Needs review",
        priority_reason="Test reason",
        status="Pending",
        created_at=datetime.now(timezone.utc).isoformat(),
        modified_at=datetime.now(timezone.utc).isoformat(),
    ))

    with pytest.raises(HTTPException) as exc_info:
        approval_svc.mark_returned(
            request_id=pending_req.id,
            actor_email=test_user.user_email,
        )
    assert exc_info.value.status_code in [400, 409]


def test_d7_normal_user_cannot_return_another_users_request(test_user, other_user):
    """Test D7: A user cannot return someone else's request (HTTPException 403)."""
    req_repo = get_request_repo()
    approval_svc = ApprovalService(req_repo, NotificationService(None))

    other_req = req_repo.create(RequestRead(
        id=0,
        requester_name=other_user.user_name,
        requester_email=other_user.user_email,
        project="Regression D7",
        equipment_id="TU1-003",
        equipment_name="Test Item D7",
        quantity=1,
        needed_from="2026-01-01",
        needed_to="2026-01-10",
        purpose="Regression test",
        priority_level="Needs review",
        priority_reason="Test reason",
        status="Borrowed",
        created_at=datetime.now(timezone.utc).isoformat(),
        modified_at=datetime.now(timezone.utc).isoformat(),
    ))

    with pytest.raises(HTTPException) as exc_info:
        approval_svc.mark_returned(
            request_id=other_req.id,
            actor_email=test_user.user_email,
        )
    assert exc_info.value.status_code == 403


def test_d8_overdue_eligible_request_remains_returnable(test_user):
    """Test D8: An overdue borrowed request remains returnable."""
    req_repo = get_request_repo()
    approval_svc = ApprovalService(req_repo, NotificationService(None))

    overdue_req = req_repo.create(RequestRead(
        id=0,
        requester_name=test_user.user_name,
        requester_email=test_user.user_email,
        project="Regression D8 Overdue",
        equipment_id="TU1-003",
        equipment_name="Test Item D8",
        quantity=1,
        needed_from="2023-01-01",
        needed_to="2023-01-10",  # In the past
        purpose="Regression test",
        priority_level="Needs review",
        priority_reason="Test reason",
        status="Borrowed",
        created_at=datetime.now(timezone.utc).isoformat(),
        modified_at=datetime.now(timezone.utc).isoformat(),
    ))

    returned_req = approval_svc.mark_returned(
        request_id=overdue_req.id,
        actor_email=test_user.user_email,
    )
    assert returned_req.status == "Returned"


# =====================================================================
# E. Context and Regression Tests (E1 - E4)
# =====================================================================

def test_e1_banana_jumper_followup_quantity(orchestrator, test_user):
    """Test E1: 'Cho mình xem Banana jumper' -> 'Cái thứ 2 có bao nhiêu cái?' retrieves quantity for item #2."""
    r1 = orchestrator.process_message("Cho mình xem Banana jumper", test_user, "conv_e1")
    assert "Banana jumper" in r1["reply"]

    r2 = orchestrator.process_message("Cái thứ 2 có bao nhiêu cái?", test_user, "conv_e1")
    assert "TU1-011" in r2["reply"]
    assert "89 cái" in r2["reply"]


def test_e2_pending_action_cancellation(orchestrator, test_user):
    """Test E2: A pending return action followed by explicit cancellation clears the action."""
    r1 = orchestrator.process_message("Mình muốn trả đồ", test_user, "conv_e2")
    st1 = state_manager.get_state(test_user.user_email, "conv_e2")
    assert st1.pending_action == "return"

    r2 = orchestrator.process_message("Thôi mình không trả nữa", test_user, "conv_e2")
    st2 = state_manager.get_state(test_user.user_email, "conv_e2")
    assert st2.pending_action is None
    assert "Đã hủy thao tác" in r2["reply"]


def test_e3_readonly_query_never_opens_borrow_form(orchestrator, test_user):
    """Test E3: A read-only detail query never opens BorrowForm solely because it mentions an equipment."""
    r1 = orchestrator.process_message("Cho mình xem thông tin TU1-001", test_user, "conv_e3_1")
    assert r1.get("action") is None

    r2 = orchestrator.process_message("TU1-001 nằm ở đâu?", test_user, "conv_e3_2")
    assert r2.get("action") is None

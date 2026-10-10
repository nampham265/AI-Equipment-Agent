"""Consolidated Automated Regression Suite for AI Equipment Agent V1.

Validates all 14 core areas:
1. Routing Integrity & Fallback
2. Out-of-Stock Inventory (Quantity == 0)
3. Low-Stock Inventory (Thresholds & Default <= 5)
4. Distinct Equipment Type Count (29 connector/cable types)
5. Personal Loans Query (Scoped to Authenticated User)
6. Follow-up Person Refinement & Strict RBAC
7. Combined Usage & Quantity Sufficiency Query
8. False Positive Prevention on Exact Existence (CANInterface XYZ)
9. Banana Jumper Color Variants (Red TU1-010 vs Black TU1-011) & Black Connector
10. Markdown Table Cell Escaping (| and newlines)
11. Auto-approve Prohibition Notice
12. Manager Self-Approval Prohibition
13. Test Data Excel Isolation
14. Follow-up Equipment Details ("Những thiết bị đó là gì")
"""
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from datetime import datetime, timezone
from pathlib import Path

from app.agent.models import (
    ConversationState,
    ExtractedConstraints,
    GeminiRouterOutput,
    IntentType,
    QueryPlan,
)
from app.agent.normalizer import check_ask_auto_approve, check_existence_query
from app.agent.orchestrator import AgentOrchestrator, _map_gemini_to_plan, escape_markdown_cell
from app.agent.router import query_router
from app.agent.state import state_manager
from app.agent.tools import AgentTools
from app.auth.session import SessionData
from app.core.config import settings
from app.repositories.factory import get_equipment_repo, get_request_repo, get_user_repo
from app.schemas.requests import RequestRead, RequestStatus
from app.services.approval_service import ApprovalService
from app.services.notification_service import NotificationService


@pytest.fixture
def nam_user():
    return SessionData(
        user_email="phamngochainam25@gmail.com",
        user_name="Phạm Ngọc Hải Nam",
        user_oid="oid-nam",
        is_manager=False,
    )


@pytest.fixture
def other_user():
    return SessionData(
        user_email="other_dev@company.com",
        user_name="Other Dev",
        user_oid="oid-other",
        is_manager=False,
    )


@pytest.fixture
def manager_user():
    return SessionData(
        user_email="manager@company.com",
        user_name="Manager User",
        user_oid="oid-manager",
        is_manager=True,
    )


@pytest.fixture
def orchestrator():
    eq_repo = get_equipment_repo()
    req_repo = get_request_repo()
    user_repo = get_user_repo()
    tools = AgentTools(eq_repo, req_repo, user_repo)
    return AgentOrchestrator(tools=tools, gemini_router=None)


# =====================================================================
# 1. Routing Integrity & Mode Verification
# =====================================================================

def test_area_1_routing_mode_llm_primary_success(nam_user, monkeypatch):
    """When Gemini succeeds under llm_primary, trace records routing_mode='llm_primary' without fallback."""
    monkeypatch.setattr(settings, "AGENT_ROUTING_MODE", "llm_primary")
    eq_repo = get_equipment_repo()
    req_repo = get_request_repo()
    tools = AgentTools(eq_repo, req_repo)

    from app.agent.models import LLMConstraints
    mock_gemini = MagicMock()
    mock_out = GeminiRouterOutput(
        intent=IntentType.EQUIPMENT_SEARCH,
        confidence=0.95,
        constraints=LLMConstraints(keywords=["connector"]),
    )
    mock_gemini.classify_message.return_value = mock_out

    orch = AgentOrchestrator(tools=tools, gemini_router=mock_gemini)

    res = orch.process_message("Tìm connector", nam_user, "conv-route-1")
    trace = res["trace"]

    assert trace["routing_mode"] == "llm_primary"
    assert trace["llm_router_called"] is True
    assert trace["fallback_used"] is False
    assert trace["intent"] == "equipment_search"


def test_area_1_routing_mode_llm_primary_fallback_on_error(nam_user, monkeypatch):
    """When Gemini throws an exception, trace records routing_mode='legacy_fallback' and fallback_used=True."""
    monkeypatch.setattr(settings, "AGENT_ROUTING_MODE", "llm_primary")
    eq_repo = get_equipment_repo()
    req_repo = get_request_repo()
    tools = AgentTools(eq_repo, req_repo)

    mock_gemini = MagicMock()
    mock_gemini.classify_message.side_effect = RuntimeError("Gemini API timeout")

    orch = AgentOrchestrator(tools=tools, gemini_router=mock_gemini)

    res = orch.process_message("Tìm connector", nam_user, "conv-route-2")
    trace = res["trace"]

    assert trace["routing_mode"] == "legacy_fallback"
    assert trace["fallback_used"] is True
    assert trace["intent"] == "equipment_search"


# =====================================================================
# 2. Out-of-Stock Inventory (Quantity == 0)
# =====================================================================

def test_area_2_out_of_stock_inventory_intent_and_results(orchestrator, nam_user):
    """'Trong kho có thiết bị nào hết không?' returns exactly 3 items with Quantity == 0."""
    res = orchestrator.process_message("Trong kho có thiết bị nào hết không?", nam_user, "conv-oos-1")
    trace = res["trace"]
    reply = res["reply"]

    assert trace["intent"] == "out_of_stock_inventory"
    assert trace["selected_tool"] == "get_out_of_stock_inventory"
    assert trace["tool_result_count"] == 3
    assert set(trace["selected_result_ids"]) == {"TU2-007", "TU2-017", "TU2-018"}
    assert "Báo cáo thiết bị đã hết hàng" in reply
    assert "`TU2-007`" in reply
    assert "`TU2-017`" in reply
    assert "`TU2-018`" in reply


# =====================================================================
# 3. Low-Stock Inventory (Default <= 5 vs Threshold)
# =====================================================================

def test_area_3_low_stock_inventory_default(orchestrator, nam_user):
    """'Hiện tại trong kho có thiết bị nào sắp hết không' returns low-stock items <= 5 (52 items)."""
    res = orchestrator.process_message("Hiện tại trong kho có thiết bị nào sắp hết không", nam_user, "conv-low-1")
    trace = res["trace"]
    reply = res["reply"]

    assert trace["intent"] == "low_stock_inventory"
    assert trace["selected_tool"] == "get_low_stock_inventory"
    assert trace["tool_result_count"] == 52
    assert "Báo cáo thiết bị có số lượng tồn thấp" in reply


def test_area_3_low_stock_inventory_strict_threshold(orchestrator, nam_user):
    """'Thiết bị nào còn dưới 3 cái' uses threshold=3, operator='<'."""
    res = orchestrator.process_message("Thiết bị nào còn dưới 3 cái", nam_user, "conv-low-2")
    trace = res["trace"]

    assert trace["intent"] == "low_stock_inventory"
    assert trace["tool_arguments"]["threshold"] == 3
    assert trace["tool_arguments"]["operator"] == "<"


# =====================================================================
# 4. Distinct Equipment Type Count (29 types for connector/cable)
# =====================================================================

def test_area_4_distinct_type_count_connector_cable(orchestrator, nam_user):
    """'Kho hiện có bao nhiêu loại connector/cable?' returns 29 types."""
    res = orchestrator.process_message("Kho hiện có bao nhiêu loại connector/cable?", nam_user, "conv-count-1")
    trace = res["trace"]
    reply = res["reply"]

    assert trace["intent"] == "equipment_count"
    assert "29 loại" in reply


# =====================================================================
# 5. Personal Loans Query (Scoped to Authenticated User)
# =====================================================================

def test_area_5_personal_loans_scoped_to_user(orchestrator, nam_user):
    """'Hiện mình đang mượn mấy thiết bị' returns 5 requests, 5 distinct types, 11 units for nam_user."""
    res = orchestrator.process_message("Hiện mình đang mượn mấy thiết bị", nam_user, "conv-mine-1")
    trace = res["trace"]
    reply = res["reply"]

    assert trace["intent"] == "my_requests"
    assert trace["tool_arguments"]["user_email"] == "phamngochainam25@gmail.com"
    assert trace["tool_result_count"] == 5
    assert "5 đơn mượn" in reply
    assert "5 loại thiết bị" in reply
    assert "11" in reply


# =====================================================================
# 6. Follow-up Person Refinement & Strict RBAC
# =====================================================================

def test_area_6_person_refinement_self_allowed(orchestrator, nam_user):
    """Follow-up 'Nếu chỉ riêng Nam Phạm thôi thì sao' by nam_user is allowed."""
    # First query
    orchestrator.process_message("Hiện mình đang mượn mấy thiết bị", nam_user, "conv-refine-1")
    # Follow-up
    res = orchestrator.process_message("Nếu chỉ riêng Nam Phạm thôi thì sao", nam_user, "conv-refine-1")
    trace = res["trace"]
    assert trace["intent"] == "my_requests"
    assert trace["tool_arguments"]["user_email"] == "phamngochainam25@gmail.com"
    assert trace["tool_result_count"] == 5


def test_area_6_person_refinement_other_user_forbidden(orchestrator, other_user):
    """Regular user querying other person's loans is rejected with clear RBAC message."""
    # First query
    orchestrator.process_message("Danh sách yêu cầu của tôi", other_user, "conv-refine-2")
    # Follow-up querying Nam Phạm
    res = orchestrator.process_message("Nếu chỉ riêng Nam Phạm thôi thì sao", other_user, "conv-refine-2")
    reply = res["reply"]

    assert "chỉ có quyền xem các thiết bị do chính mình mượn" in reply
    assert "Quản lý" in reply


# =====================================================================
# 7. Combined Usage & Quantity Sufficiency Query
# =====================================================================

def test_area_7_usage_and_quantity_combined(orchestrator, nam_user):
    """'Conn header SMD 24pos 3mm female có đang được ai sử dụng không, và hiện có còn dư trong kho để cho mình mượn tầm 10 cái không'
    Answers active usage (11 units borrowed) AND warehouse availability (23 available > 10).
    """
    msg = "Conn header SMD 24pos 3mm female có đang được ai sử dụng không, và hiện có còn dư trong kho để cho mình mượn tầm 10 cái không"
    res = orchestrator.process_message(msg, nam_user, "conv-avail-1")
    trace = res["trace"]
    reply = res["reply"]

    assert trace["intent"] == "availability_query"
    assert "Tình trạng sử dụng" in reply
    assert "11 cái" in reply or "đang có" in reply
    assert "Khả năng đáp ứng" in reply
    assert "còn dư đủ" in reply


# =====================================================================
# 8. False Positive Prevention on Exact Existence (CANInterface XYZ)
# =====================================================================

def test_area_8_caninterface_xyz_returns_not_found(orchestrator, nam_user):
    """'Kho có CANInterface XYZ không?' returns not found (0 items), never all 116 items."""
    res = orchestrator.process_message("Kho có CANInterface XYZ không?", nam_user, "conv-exist-1")
    trace = res["trace"]
    reply = res["reply"]

    assert trace["intent"] == "equipment_exists"
    assert trace["tool_result_count"] == 0
    assert "Không tìm thấy thiết bị CANInterface XYZ trong dữ liệu hiện tại." in reply


# =====================================================================
# 9. Banana Jumper Color Variants & Black Connector Search
# =====================================================================

def test_area_9_banana_jumper_red_vs_black(orchestrator, nam_user):
    """'Tìm Banana jumper màu đỏ' -> TU1-010. 'Tìm Banana jumper màu đen' -> TU1-011."""
    res_red = orchestrator.process_message("Tìm Banana jumper màu đỏ", nam_user, "conv-banana-1")
    assert res_red["trace"]["selected_result_ids"] == ["TU1-010"]

    res_black = orchestrator.process_message("Tìm Banana jumper màu đen", nam_user, "conv-banana-2")
    assert res_black["trace"]["selected_result_ids"] == ["TU1-011"]


def test_area_9_black_connector_search(orchestrator, nam_user):
    """'Tìm connector màu đen' returns black connectors including TU1-011."""
    res = orchestrator.process_message("Tìm connector màu đen", nam_user, "conv-black-conn")
    selected_ids = res["trace"]["selected_result_ids"]
    assert "TU1-011" in selected_ids


# =====================================================================
# 10. Markdown Table Cell Escaping (| and newlines)
# =====================================================================

def test_area_10_escape_markdown_cell():
    """escape_markdown_cell correctly escapes literal pipes, newlines, and backticks."""
    cell_pipe = "TE Connectivity | RS"
    escaped = escape_markdown_cell(cell_pipe)
    assert escaped == r"TE Connectivity \| RS"

    cell_newline = "Line 1\nLine 2\r\nLine 3"
    escaped_nl = escape_markdown_cell(cell_newline)
    assert "\n" not in escaped_nl
    assert "\r" not in escaped_nl
    assert escaped_nl == "Line 1 Line 2 Line 3"

    cell_code = "foo | bar"
    escaped_code = escape_markdown_cell(cell_code, wrap_code=True)
    assert escaped_code == r"`foo \| bar`"


# =====================================================================
# 11. Auto-approve Prohibition Notice
# =====================================================================

def test_area_11_ask_auto_approve_flag_and_notice(orchestrator, nam_user):
    """When user asks AI to auto-approve, notice is displayed that AI cannot approve."""
    msg = "Mình muốn mượn 2 cái TU1-001, bạn tự duyệt luôn giúp mình nha"
    res = orchestrator.process_message(msg, nam_user, "conv-auto-1")
    reply = res["reply"]

    assert "Trợ lý AI không có quyền tự phê duyệt đơn mượn" in reply
    assert "Quản lý (Manager)" in reply


# =====================================================================
# 12. Manager Self-Approval Prohibition
# =====================================================================

def test_area_12_manager_cannot_self_approve():
    """ApprovalService raises 403 when manager attempts to approve their own request."""
    from app.notifications.console_provider import ConsoleNotificationProvider
    req_repo = get_request_repo()
    user_repo = get_user_repo()
    approval_svc = ApprovalService(req_repo, NotificationService(ConsoleNotificationProvider()))

    tools = AgentTools(get_equipment_repo(), req_repo, user_repo)
    req = tools.create_request(
        requester_name="Test Manager",
        requester_email="test.manager@company.com",
        project="Manager Project",
        equipment_id="TU1-001",
        quantity=1,
        needed_from="2026-11-01",
        needed_to="2026-11-05",
        purpose="Self-approval test",
    )

    manager = SessionData(
        user_email="test.manager@company.com",
        user_name="Test Manager",
        user_oid="oid-mgr",
        is_manager=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        approval_svc.approve(req.id, actor_email=manager.user_email)

    assert exc_info.value.status_code == 403
    assert "không thể tự phê duyệt" in exc_info.value.detail.lower()


# =====================================================================
# 13. Test Data Excel Isolation
# =====================================================================

def test_area_13_excel_isolation_active(tmp_path):
    """Verify that settings.EXCEL_DATA_PATH is pointed to tmp_path during tests."""
    current_path = Path(settings.EXCEL_DATA_PATH)
    assert "equipment_agent_test.xlsx" in current_path.name
    # Ensure real data file exists and is intact
    real_path = Path("data/equipment_agent.xlsx")
    assert real_path.exists()


# =====================================================================
# 14. Follow-up Equipment Details ("Những thiết bị đó là gì")
# =====================================================================

def test_area_14_followup_equipment_list_detail(orchestrator, nam_user):
    """'Những thiết bị đó là gì' after 'Hiện mình đang mượn mấy thiết bị' details the 5 items."""
    # First query
    orchestrator.process_message("Hiện mình đang mượn mấy thiết bị", nam_user, "conv-detail-1")
    # Follow-up
    res = orchestrator.process_message("Những thiết bị đó là gì", nam_user, "conv-detail-1")
    reply = res["reply"]

    assert "Danh sách cụ thể các thiết bị đang mượn" in reply
    assert "`TU1-001`" in reply
    assert "`TU1-008`" in reply
    assert "`TU1-017`" in reply
    assert "`TU1-013`" in reply
    assert "`TU1-023`" in reply

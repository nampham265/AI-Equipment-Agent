"""Comprehensive Test Suite for Post-Audit Delta Implementation.

Covers all 9 specific requirements:
1. Gemini runtime mode verification (trace fields, routing modes).
2. Personal active-loan queries and person refinement filters with strict RBAC.
3. Quantity sufficiency, usage evaluation, shortage calculation, and follow-ups.
4. Return flow: listing borrowed requests, ordinal resolution, and name matching.
5. Distinct low-stock vs out-of-stock reporting and operator parsing.
6. Multi-variant listings (Banana jumper), color constraints, type counts, and pipe escaping.
"""
from __future__ import annotations

import re
import pytest
from app.agent.models import ConversationState, ExtractedConstraints, IntentType
from app.agent.orchestrator import AgentOrchestrator
from app.agent.router import query_router
from app.agent.tools import AgentTools
from app.auth.session import SessionData
from app.core.config import settings
from app.repositories.excel_equipment import ExcelEquipmentRepository
from app.repositories.excel_request import ExcelRequestRepository
from app.repositories.excel_user import ExcelUserRepository


@pytest.fixture
def agent_system():
    excel_path = settings.resolved_excel_path
    eq_repo = ExcelEquipmentRepository(excel_path)
    req_repo = ExcelRequestRepository(excel_path)
    user_repo = ExcelUserRepository(excel_path)
    tools = AgentTools(eq_repo, req_repo, user_repo=user_repo)
    orch = AgentOrchestrator(tools=tools)
    return {
        "eq_repo": eq_repo,
        "req_repo": req_repo,
        "user_repo": user_repo,
        "tools": tools,
        "orchestrator": orch,
    }


# ==============================================================================
# 1. Gemini Runtime Verification & Trace
# ==============================================================================
def test_01_gemini_trace_and_routing_fields(agent_system):
    orch = agent_system["orchestrator"]
    user = SessionData(user_email="test@example.com", user_name="Test User", role="USER")

    # In test environment (legacy_only), verify trace captures routing_mode and fallback flags cleanly
    res = orch.process_message("Kho có bao nhiêu cáp nối?", user, "trace_conv")
    trace = res["trace"]
    assert trace is not None
    assert "routing_mode" in trace
    assert trace["routing_mode"] in ["legacy_only", "llm_primary", "legacy_fallback"]
    assert "llm_router_called" in trace
    assert "fallback_used" in trace
    assert "query_plan" in trace
    assert trace["intent"] == "equipment_count"


# ==============================================================================
# 2. Personal Active-Loan Queries & Person Filters
# ==============================================================================
def test_02_personal_loan_and_person_filter(agent_system):
    orch = agent_system["orchestrator"]
    user = SessionData(
        user_email="phamngochainam25@gmail.com",
        user_name="Nam Phạm",
        role="USER",
    )

    # 1. User asks for their own active loans
    res1 = orch.process_message("Hiện mình đang mượn mấy thiết bị", user, "conv_p1")
    assert res1["trace"]["intent"] == "my_requests"
    assert res1["trace"]["query_plan"].get("status_filter") == "Borrowed"
    assert "đang trong trạng thái mượn (Borrowed)" in res1["reply"] or "đơn mượn" in res1["reply"]

    # 2. Follow-up: "Nếu chỉ riêng Nam Phạm thôi thì sao"
    res2 = orch.process_message("Nếu chỉ riêng Nam Phạm thôi thì sao", user, "conv_p1")
    assert res2["trace"]["intent"] == "my_requests"
    assert "đang trong trạng thái mượn (Borrowed)" in res2["reply"] or "đơn mượn" in res2["reply"]

    # 3. Regular user asks about another person -> 403 / permission notice
    res3 = orch.process_message("Nếu chỉ riêng Nguyen Van A thôi thì sao", user, "conv_p1")
    assert "Chỉ có quyền xem các thiết bị do chính mình mượn" in res3["reply"] or "Quản lý (Manager)" in res3["reply"]


def test_02b_manager_active_loans_person_filter(agent_system):
    orch = agent_system["orchestrator"]
    manager = SessionData(
        user_email="manager@company.com",
        user_name="Manager Test",
        role="MANAGER",
    )

    # Manager asks for all active borrowers, then filters by person
    m1 = orch.process_message("Hiện có những ai đang mượn thiết bị", manager, "conv_m1")
    assert m1["trace"]["intent"] in ["active_borrowers", "active_borrowers_count"]

    m2 = orch.process_message("Nếu chỉ riêng Nam Phạm thôi thì sao", manager, "conv_m1")
    assert m2["trace"]["intent"] == "active_loans"
    assert "Danh sách" in m2["reply"]
    assert "Phạm Ngọc Hải Nam" in m2["reply"]
    # Manager should only see Nam Pham's loans, not other borrowers' rows
    assert "Overdue Borrower" not in m2["reply"]


# ==============================================================================
# 3. Quantity Sufficiency, Usage, and Follow-ups
# ==============================================================================
def test_03_quantity_sufficiency_and_followup_flow(agent_system):
    orch = agent_system["orchestrator"]
    user = SessionData(
        user_email="phamngochainam25@gmail.com",
        user_name="Nam Phạm",
        role="USER",
    )

    # Turn 1: Availability & usage question
    msg1 = "Conn header SMD 24pos 3mm female có đang được ai sử dụng không, và hiện có còn dư trong kho để cho mình mượn tầm 10 cái không"
    r1 = orch.process_message(msg1, user, "conv_flow")
    assert r1["trace"]["intent"] == "availability_query"
    assert "TU1-001" in r1["reply"]
    assert "Tình trạng sử dụng" in r1["reply"]
    assert "Số lượng khả dụng" in r1["reply"]
    assert "10 cái" in r1["reply"]

    # Turn 2: Follow-up hypothetical for 30 units (shortage)
    msg2 = "Nếu mình cần mượn 30 cái thì sao?"
    r2 = orch.process_message(msg2, user, "conv_flow")
    assert r2["trace"]["intent"] == "availability_query"
    assert "TU1-001" in r2["reply"]
    assert "30 cái" in r2["reply"]
    assert "không đủ" in r2["reply"].lower() or "thiếu" in r2["reply"].lower()

    # Turn 3: Follow-up hypothetical for 5 units (sufficient)
    msg3 = "Nếu chỉ mượn 5 cái thì sao?"
    r3 = orch.process_message(msg3, user, "conv_flow")
    assert r3["trace"]["intent"] == "availability_query"
    assert "TU1-001" in r3["reply"]
    assert "5 cái" in r3["reply"]
    assert "còn dư đủ" in r3["reply"].lower()

    # Turn 4: Create borrow request for the active equipment
    msg4 = "Vậy tạo đơn mượn 5 cái"
    r4 = orch.process_message(msg4, user, "conv_flow")
    assert r4["action"] is not None
    assert r4["action"]["type"] == "show_borrow_form"
    assert r4["action"]["prefill"]["equipment_id"] == "TU1-001"
    assert r4["action"]["prefill"]["quantity"] == 5


def test_03b_direct_large_quantity_shortage(agent_system):
    orch = agent_system["orchestrator"]
    user = SessionData(user_email="test@example.com", user_name="Test User", role="USER")

    msg = "Mình cần mượn 50 cái Conn header SMD 24pos 3mm female thì kho có đủ không"
    res = orch.process_message(msg, user, "conv_shortage")
    assert res["trace"]["intent"] == "quantity_sufficiency"
    reply_low = res["reply"].lower()
    assert "không đủ" in reply_low
    assert "thiếu" in reply_low


# ==============================================================================
# 4. Return-Flow Regression Tests
# ==============================================================================
def test_04_return_flow_and_ordinal_resolution(agent_system):
    orch = agent_system["orchestrator"]
    user = SessionData(
        user_email="phamngochainam25@gmail.com",
        user_name="Nam Phạm",
        role="USER",
    )

    # Step 1: User says wants to return equipment
    r1 = orch.process_message("Mình muốn trả đồ", user, "conv_ret")
    assert r1["trace"]["intent"] == "return_request"
    assert "yêu cầu mượn đang hoạt động" in r1["reply"]

    # Step 2: Ordinal selection
    r2 = orch.process_message("Tôi muốn trả cái thứ 1", user, "conv_ret")
    assert r2["trace"]["intent"] == "return_request"
    assert r2["action"] is not None
    assert r2["action"]["type"] == "show_return_form"
    assert r2["action"]["prefill"]["equipment_id"] == "TU1-001"

    # Step 3: Name-based matching for return
    r3 = orch.process_message("Mình muốn trả Conn 4.2mm", user, "conv_ret_name")
    assert r3["trace"]["intent"] == "return_request"
    assert r3["action"] is not None
    assert r3["action"]["type"] == "show_return_form"
    assert "4.2mm" in r3["action"]["prefill"]["equipment_name"] or r3["action"]["prefill"]["equipment_id"] in ["TU1-002", "TU1-008", "TU1-012"]


# ==============================================================================
# 5. Low-Stock vs Out-of-Stock Reporting
# ==============================================================================
def test_05_low_stock_and_out_of_stock_distinction(agent_system):
    orch = agent_system["orchestrator"]
    user = SessionData(user_email="test@example.com", user_name="Test User", role="USER")

    # 1. Out of stock (Quantity == 0)
    o1 = orch.process_message("Trong kho có thiết bị nào đã hết hàng không?", user, "c_out")
    assert o1["trace"]["intent"] == "out_of_stock_inventory"

    # 2. Low stock without threshold
    l1 = orch.process_message("Hiện tại trong kho có thiết bị nào sắp hết không?", user, "c_low")
    assert l1["trace"]["intent"] == "low_stock_inventory"
    assert l1["trace"]["query_plan"]["low_stock_threshold"] is None

    # 3. Strict less-than threshold (< 5)
    l2 = orch.process_message("Trong kho có thiết bị nào còn dưới 5 cái không?", user, "c_strict")
    assert l2["trace"]["intent"] == "low_stock_inventory"
    assert l2["trace"]["query_plan"]["low_stock_threshold"] == 5
    assert l2["trace"]["query_plan"]["low_stock_operator"] == "<"

    # 4. Less-than-or-equal threshold (<= 5)
    l3 = orch.process_message("Trong kho có món nào 5 cái trở xuống không?", user, "c_inc")
    assert l3["trace"]["intent"] == "low_stock_inventory"
    assert l3["trace"]["query_plan"]["low_stock_threshold"] == 5
    assert l3["trace"]["query_plan"]["low_stock_operator"] == "<="


# ==============================================================================
# 6. Multi-variant, Color, Type Count, and Pipe Escaping
# ==============================================================================
def test_06_retrieval_and_formatting_details(agent_system):
    orch = agent_system["orchestrator"]
    user = SessionData(user_email="test@example.com", user_name="Test User", role="USER")

    # Banana jumper variants
    b_res = orch.process_message("Kho có banana jumper không?", user, "c_banana")
    assert "TU1-010" in b_res["reply"] or "TU1-011" in b_res["reply"]

    # Black connector
    c_res = orch.process_message("Tìm connector màu đen", user, "c_black")
    assert "TU1-001" in c_res["reply"]

    # Distinct connector types count
    t_res = orch.process_message("Kho có bao nhiêu loại connector?", user, "c_types")
    assert "loại" in t_res["reply"]

    # Table cell pipe escaping
    p_res = orch.process_message("Báo cáo các thiết bị sắp hết", user, "c_pipe")
    assert "\\|" in p_res["reply"]

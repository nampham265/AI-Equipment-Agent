"""Comprehensive Regression and Audit Remediation Test Suite.

Covers all 14 test scenarios from the audit report:
1. cục ABS precision (no smoke absorber, no wheelspeed sensor)
2. banana jumper màu đỏ precision (no PLA red filament)
3. Connector 4.2mm góc vuông Tủ 1 hard constraints (TU1-002, TU1-008, TU1-012)
4. Nonexistent equipment (CANInterface XYZ -> 0 results, no warehouse fallback)
5. Context bleeding prevention (TU2-007 query -> borrow banana jumper opens banana jumper)
6. Relative natural dates and form prefill (needed_from, needed_to, project, equipment_id)
7. Alternative search for TU2-007 (EBS-032 suitable, holders & connectors are accessories)
8. Distinction between description similarity and technical compatibility
9. Return flow condition notes extraction and prefill
10. Return flow quantity clarification for multi-unit loans
11. Regular user asking pending request count (scoped to user, not blocked)
12. Manager asking pending request count (actionable + self-pending breakdown)
13. Inventory inconsistency detection (CSW-001 borrowed 6 > total 5 triggers warning)
14. Strict low-stock operator (< 3)
"""
from __future__ import annotations

import re
from datetime import date, datetime
import pytest

from app.agent.models import ConversationState, ExtractedConstraints, IntentType
from app.agent.orchestrator import AgentOrchestrator
from app.agent.retrieval import HybridRetrievalService
from app.agent.router import query_router
from app.agent.tools import AgentTools, classify_equipment_role
from app.auth.session import SessionData
from app.repositories.excel_equipment import ExcelEquipmentRepository
from app.repositories.excel_request import ExcelRequestRepository
from app.repositories.excel_user import ExcelUserRepository
from app.core.config import settings


@pytest.fixture
def agent_setup():
    excel_path = settings.resolved_excel_path
    eq_repo = ExcelEquipmentRepository(excel_path)
    req_repo = ExcelRequestRepository(excel_path)
    user_repo = ExcelUserRepository(excel_path)
    tools = AgentTools(eq_repo, req_repo, user_repo=user_repo)
    orchestrator = AgentOrchestrator(tools=tools)
    return {
        "eq_repo": eq_repo,
        "req_repo": req_repo,
        "user_repo": user_repo,
        "tools": tools,
        "orchestrator": orchestrator,
    }


# ==============================================================================
# Scenario 1: Entity Precision — "cục ABS"
# ==============================================================================
def test_01_cuc_abs_precision(agent_setup):
    tools = agent_setup["tools"]
    constraints = ExtractedConstraints(keywords=["abs"])
    results = tools.search_equipment(constraints, query="cục ABS")
    ids = [r.equipment_id for r in results]

    # Must contain ECU ABS items and Connector ABS items
    assert any("CSW" in eid for eid in ids), f"ECU ABS should be matched: {ids}"
    assert any("EBS-030" in eid or "EBS-037" in eid for eid in ids), f"Connector ABS should be matched: {ids}"

    # Must NOT contain Smoke Absorber (EBS-034) or Wheelspeed sensor (TU2-007)
    assert "EBS-034" not in ids, "EBS-034 (Smoke Absorber) must NOT match 'cục ABS'"
    assert "TU2-007" not in ids, "TU2-007 (Wheelspeed sensor) must NOT match 'cục ABS'"


# ==============================================================================
# Scenario 2: Hardware vs Color — "banana jumper màu đỏ"
# ==============================================================================
def test_02_banana_jumper_red_precision(agent_setup):
    tools = agent_setup["tools"]
    constraints = ExtractedConstraints(keywords=["banana", "jumper"], color="đỏ")
    results = tools.search_equipment(constraints, query="banana jumper màu đỏ")
    ids = [r.equipment_id for r in results]

    # Must contain banana jumper hardware (TU1-010)
    assert "TU1-010" in ids, f"Banana jumper TU1-010 should be found: {ids}"

    # Must NOT contain PLA Red 3D printing filament (EBS-011)
    assert "EBS-011" not in ids, "EBS-011 (Cuộn nhựa PLA màu đỏ) must NOT match banana jumper query"


# ==============================================================================
# Scenario 3: Multi-constraint Precision — "Connector 4.2mm góc vuông Tủ 1"
# ==============================================================================
def test_03_connector_multiconstraint_precision(agent_setup):
    tools = agent_setup["tools"]
    constraints = ExtractedConstraints(
        keywords=["connector"],
        size_mm=4.2,
        geometry="góc vuông",
        location="Tủ 1",
    )
    results = tools.search_equipment(constraints, query="Connector 4.2mm góc vuông Tủ 1")
    ids = set(r.equipment_id for r in results)

    # Must match the 3 exact items in Tủ 1 with 4.2mm right-angle header
    expected = {"TU1-002", "TU1-008", "TU1-012"}
    assert expected.issubset(ids), f"Expected {expected} in {ids}"


# ==============================================================================
# Scenario 4: Nonexistent Equipment — "CANInterface XYZ"
# ==============================================================================
def test_04_nonexistent_equipment(agent_setup):
    orchestrator = agent_setup["orchestrator"]
    user = SessionData(user_email="user@example.com", user_name="Regular User", role="USER")

    res = orchestrator.process_message(
        raw_message="Kho có CANInterface XYZ không?",
        conversation_id="conv-nonexistent",
        user=user,
    )

    reply = res["reply"]
    # Must explicitly state not found, NOT dump warehouse inventory
    assert "không tìm thấy" in reply.lower() or "không có" in reply.lower(), f"Unexpected reply: {reply}"
    assert "CSW-001" not in reply
    assert "TU1-001" not in reply


# ==============================================================================
# Scenario 5: Context Bleeding Prevention
# ==============================================================================
def test_05_context_bleeding_prevention(agent_setup):
    orchestrator = agent_setup["orchestrator"]
    user = SessionData(user_email="user@example.com", user_name="Regular User", role="USER")
    conv_id = "conv-context-bleed"

    # Turn 1: User asks about Wheelspeed sensor TU2-007
    res1 = orchestrator.process_message(
        raw_message="TU2-007 còn bao nhiêu cái?",
        conversation_id=conv_id,
        user=user,
    )
    assert "TU2-007" in res1["reply"]

    # Turn 2: User asks to borrow banana jumper red
    res2 = orchestrator.process_message(
        raw_message="Cho tôi mượn banana jumper màu đỏ",
        conversation_id=conv_id,
        user=user,
    )

    # Must open form or show selection for Banana Jumper, NOT TU2-007!
    if "action" in res2 and res2["action"]:
        prefill = res2["action"]["prefill"]
        assert prefill.get("equipment_id") != "TU2-007", f"Stale TU2-007 leaked into prefill: {prefill}"
        assert "TU1-010" in prefill.get("equipment_id", "") or "banana" in prefill.get("equipment_name", "").lower()
    else:
        assert "TU2-007" not in res2["reply"]
        assert "banana" in res2["reply"].lower()


# ==============================================================================
# Scenario 6: Natural Relative Date Parsing and Form Prefill
# ==============================================================================
def test_06_natural_date_and_borrow_prefill(agent_setup):
    orchestrator = agent_setup["orchestrator"]
    user = SessionData(user_email="user@example.com", user_name="Regular User", role="USER")

    res = orchestrator.process_message(
        raw_message="Tôi muốn mượn TU1-001 từ thứ 2 tuần sau đến cuối tuần sau cho dự án ADAS",
        conversation_id="conv-borrow-prefill",
        user=user,
    )

    assert "action" in res and res["action"] is not None
    action = res["action"]
    assert action["type"] == "show_borrow_form"
    prefill = action["prefill"]

    assert prefill["equipment_id"] == "TU1-001"
    assert prefill["project"] == "ADAS"

    # Check dates are valid ISO strings YYYY-MM-DD
    assert prefill["needed_from"] is not None
    assert prefill["needed_to"] is not None
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", prefill["needed_from"])
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", prefill["needed_to"])
    assert prefill["needed_to"] >= prefill["needed_from"]


# ==============================================================================
# Scenario 7: Grounded Alternative Search for TU2-007
# ==============================================================================
def test_07_alternative_search_grounded(agent_setup):
    tools = agent_setup["tools"]
    res = tools.search_alternative_equipment("TU2-007")

    assert res["success"] is True
    # Target item must NEVER be in alternatives
    alt_ids = [a["equipment"].equipment_id for a in res["alternatives"]]
    assert "TU2-007" not in alt_ids, "Target TU2-007 must never be in its own alternatives"

    # EBS-032 (WSS Continental) is the interchangeable sensor candidate
    assert "EBS-032" in alt_ids, f"EBS-032 must be suggested as alternative: {alt_ids}"
    ebs32_entry = next(a for a in res["alternatives"] if a["equipment"].equipment_id == "EBS-032")
    assert ebs32_entry["compatibility_status"] == "POTENTIALLY_SUITABLE"
    assert ebs32_entry["is_interchangeable"] is True
    assert "datasheet" in ebs32_entry["suitability_label"].lower() or "datasheet" in ebs32_entry["technical_note"].lower()

    # Holders and connectors must be classified as ACCESSORY_NOT_SUBSTITUTE
    for alt in res["alternatives"]:
        eq_id = alt["equipment"].equipment_id
        if eq_id in ["TU2-010", "TU2-011", "TU2-017"]:
            assert alt["compatibility_status"] == "ACCESSORY_NOT_SUBSTITUTE"
            assert alt["is_interchangeable"] is False
            assert alt["score"] <= 35, f"Accessory score should be capped <= 35, got {alt['score']}"


# ==============================================================================
# Scenario 8: Technical Report Formatting for Alternatives
# ==============================================================================
def test_08_alternative_search_distinguishes_similarity_and_compatibility(agent_setup):
    orchestrator = agent_setup["orchestrator"]
    user = SessionData(user_email="user@example.com", user_name="Regular User", role="USER")

    res = orchestrator.process_message(
        raw_message="Có thiết bị nào thay thế được cho TU2-007 không?",
        conversation_id="conv-alt-report",
        user=user,
    )

    reply = res["reply"]
    # Check structured sections
    assert "Tiềm năng thay thế" in reply or "tiềm năng thay thế" in reply.lower()
    assert "Phụ kiện" in reply or "phụ kiện" in reply.lower()
    assert "EBS-032" in reply
    assert "TU2-007" not in [line for line in reply.split("\n") if "•" in line and "TU2-007" in line]


# ==============================================================================
# Scenario 9: Return Flow Condition Notes
# ==============================================================================
def test_09_return_flow_condition_notes(agent_setup):
    orchestrator = agent_setup["orchestrator"]
    tools = agent_setup["tools"]
    user_email = "user1@example.com"
    user = SessionData(user_email=user_email, user_name="User One", role="USER")

    # Ensure user has a borrowed request
    borrowed = tools.get_active_loans_for_user(user_email)
    if not borrowed:
        # Create a borrowed request for testing
        req = tools.create_request(
            requester_name="User One",
            requester_email=user_email,
            project="ProjTest",
            equipment_id="TU1-001",
            quantity=1,
            needed_from="2026-10-01",
            needed_to="2026-10-20",
            purpose="Testing return flow",
        )
        tools.approval_service.approve(req.id, "Manager")
        tools.approval_service.mark_borrowed(req.id, "Manager")

    res = orchestrator.process_message(
        raw_message="Tôi muốn trả thiết bị này, tình trạng thiết bị còn hoạt động tốt và không bị trầy xước",
        conversation_id="conv-return-cond",
        user=user,
    )

    assert "action" in res and res["action"] is not None
    action = res["action"]
    assert action["type"] == "show_return_form"
    prefill = action["prefill"]

    # Condition notes must be prefilled
    assert "tình trạng" in prefill.get("condition_notes", "").lower() or "hoạt động tốt" in prefill.get("condition_notes", "").lower()


# ==============================================================================
# Scenario 10: Return Flow Quantity Clarification
# ==============================================================================
def test_10_return_flow_quantity_clarification(agent_setup):
    orchestrator = agent_setup["orchestrator"]
    tools = agent_setup["tools"]
    user_email = "multiuser@example.com"
    user = SessionData(user_email=user_email, user_name="Multi User", role="USER")

    # Create a borrowed request with quantity 5
    req = tools.create_request(
        requester_name="Multi User",
        requester_email=user_email,
        project="MultiProj",
        equipment_id="TU1-002",
        quantity=5,
        needed_from="2026-10-01",
        needed_to="2026-10-20",
        purpose="Multi-unit testing",
    )
    tools.approval_service.approve(req.id, "Manager")
    tools.approval_service.mark_borrowed(req.id, "Manager")

    res = orchestrator.process_message(
        raw_message="Tôi muốn trả TU1-002",
        conversation_id="conv-return-multi",
        user=user,
    )

    reply = res["reply"]
    # Must clarify quantity (5 cái) and option to adjust or return partial
    assert "5" in reply
    assert "từng phần" in reply or "điều chỉnh" in reply or "5 cái" in reply


# ==============================================================================
# Scenario 11: Regular User Pending Request Count (Scoped, Not Blocked)
# ==============================================================================
def test_11_regular_user_pending_request_count(agent_setup):
    orchestrator = agent_setup["orchestrator"]
    user = SessionData(user_email="user@example.com", user_name="Regular User", role="USER")

    res = orchestrator.process_message(
        raw_message="Hiện có bao nhiêu đơn đang chờ duyệt?",
        conversation_id="conv-user-pending",
        user=user,
    )

    reply = res["reply"]
    # Must NOT block regular user with "Chỉ quản lý mới có quyền"
    assert "Chỉ quản lý" not in reply, f"Regular user was blocked inappropriately: {reply}"
    assert "bạn" in reply.lower(), f"Response should be addressed to the user: {reply}"


# ==============================================================================
# Scenario 12: Manager Pending Request Count
# ==============================================================================
def test_12_manager_pending_request_count(agent_setup):
    orchestrator = agent_setup["orchestrator"]
    manager = SessionData(user_email="manager@bosch.com", user_name="Manager User", role="MANAGER")

    res = orchestrator.process_message(
        raw_message="Hiện có bao nhiêu đơn đang chờ duyệt?",
        conversation_id="conv-mgr-pending",
        user=manager,
    )

    reply = res["reply"]
    # Manager receives actionable pending count
    assert "đơn" in reply.lower()
    assert "phê duyệt" in reply.lower() or "chờ" in reply.lower()


# ==============================================================================
# Scenario 13: Inventory Inconsistency Detection
# ==============================================================================
def test_13_inventory_inconsistency_detection(agent_setup):
    tools = agent_setup["tools"]
    # CSW-001 has quantity_total = 5, but active borrowed requests sum to 6 in initial dataset
    info = tools.get_equipment_count("CSW-001")
    assert info["found"] is True
    assert info["has_inconsistency"] is True, f"CSW-001 should flag inconsistency: {info}"
    assert info["inconsistency_note"] is not None
    assert "bất thường" in info["inconsistency_note"].lower()

    # Also check orchestrator response
    orchestrator = agent_setup["orchestrator"]
    user = SessionData(user_email="user@example.com", user_name="User", role="USER")
    res = orchestrator.process_message(
        raw_message="CSW-001 còn bao nhiêu cái?",
        conversation_id="conv-inconsistency",
        user=user,
    )
    assert "bất thường" in res["reply"].lower() or "cảnh báo" in res["reply"].lower()


# ==============================================================================
# Scenario 14: Strict Low-stock Operator (< 3)
# ==============================================================================
def test_14_low_stock_strict_operator(agent_setup):
    orchestrator = agent_setup["orchestrator"]
    user = SessionData(user_email="user@example.com", user_name="User", role="USER")

    res = orchestrator.process_message(
        raw_message="Trong kho có thiết bị nào còn dưới 3 cái không?",
        conversation_id="conv-low-stock-strict",
        user=user,
    )

    trace = res.get("trace", {})
    assert trace.get("selected_tool") == "get_low_stock_inventory"
    reply = res["reply"]
    assert "dưới 3" in reply

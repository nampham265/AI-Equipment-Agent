"""Tests for Schedule Conflict Chat Presentation, Markdown Table, and AI Decision Support."""
from __future__ import annotations

import pytest
from app.agent.orchestrator import AgentOrchestrator
from app.agent.tools import AgentTools
from app.auth.session import SessionData
from app.core.config import settings
from app.repositories.excel_equipment import ExcelEquipmentRepository
from app.repositories.excel_request import ExcelRequestRepository
from app.services.conflict_service import ConflictService, format_date_vn


@pytest.fixture
def agent_setup():
    excel_path = settings.resolved_excel_path
    eq_repo = ExcelEquipmentRepository(str(excel_path))
    req_repo = ExcelRequestRepository(str(excel_path))
    tools = AgentTools(eq_repo, req_repo)
    orchestrator = AgentOrchestrator(tools)
    user = SessionData(
        user_email="manager@company.com",
        user_name="Test Manager",
        user_oid="mgr-123",
        is_manager=True,
    )
    return orchestrator, tools, user


def test_conflict_service_enriched_fields():
    """Verify ConflictService outputs enriched fields with Vietnamese dates and priority metadata."""
    excel_path = settings.resolved_excel_path
    eq_repo = ExcelEquipmentRepository(str(excel_path))
    req_repo = ExcelRequestRepository(str(excel_path))

    all_reqs = req_repo.list_all()
    all_eq = eq_repo.list_all()
    eq_map = {eq.equipment_id: eq.equipment_name for eq in all_eq}

    svc = ConflictService()
    pairs = svc.find_conflict_pairs(all_reqs, eq_map)

    assert len(pairs) >= 3, f"Expected at least 3 canonical conflict pairs, got {len(pairs)}"

    for p in pairs:
        assert "pair_key" in p
        assert "equipment_id" in p
        assert "equipment_name" in p
        # Enriched fields
        assert "quantity_a" in p
        assert "quantity_b" in p
        assert "priority_level_a" in p
        assert "priority_level_b" in p
        assert "needed_from_a_vn" in p
        assert "needed_to_a_vn" in p
        assert "needed_from_b_vn" in p
        assert "needed_to_b_vn" in p
        assert "overlap_duration" in p

        # Verify VN date format contains '/'
        assert "/" in p["needed_from_a_vn"]
        assert "/" in p["needed_to_a_vn"]


def test_conflict_chat_table_format_and_ai_decision_support(agent_setup):
    """Verify that asking about schedule conflicts produces a clean Markdown table,
    dates in DD/MM/YYYY, AI recommendations, and manager governance guidance."""
    orchestrator, tools, user = agent_setup

    query = "Hiện tại có bao nhiêu request mượn thiết bị bị trùng lịch"
    result = orchestrator.process_message(
        raw_message=query,
        user=user,
        conversation_id="conv-test-1",
    )
    response = result["reply"]

    # 1. Heading and Count reconciliation
    assert "3 cặp xung đột lịch" in response or "cặp xung đột lịch" in response

    # 2. Markdown Table headers and structure
    assert "| STT | Thiết bị | Đơn cần duyệt (A) |" in response
    assert "|:---:|:---|:---|:---|:---|:---|:---|" in response
    assert "Khoảng trùng lịch" in response

    # 3. Formatted dates in DD/MM/YYYY
    assert "/2026" in response  # Dates formatted as DD/MM/YYYY

    # 4. AI Decision Support section
    assert "Phân tích & Đề xuất giải quyết từ AI" in response
    assert "Đánh giá tồn kho" in response
    assert "Khuyến nghị AI" in response

    # 5. Governance Rule (Manager decides, AI assists)
    assert "Nguyên tắc quản trị" in response
    assert "AI chỉ hỗ trợ" in response or "AI chỉ tổng hợp" in response
    assert "Quản lý" in response

    # 6. Quick Action commands
    assert "Duyệt đơn #" in response
    assert "Từ chối đơn #" in response


def test_conflict_borrowers_followup_flow(agent_setup):
    """Verify that following up with 'Những người đó là ai' returns the list of people involved."""
    orchestrator, tools, user = agent_setup
    conv_id = "conv-test-followup"

    # First turn: conflict query
    res1 = orchestrator.process_message(
        raw_message="Hiện tại có bao nhiêu request mượn thiết bị bị trùng lịch",
        user=user,
        conversation_id=conv_id,
    )
    reply1 = res1["reply"]
    assert "xung đột lịch" in reply1.lower()

    # Second turn: follow-up inquiry about the people involved using same conversation_id
    res2 = orchestrator.process_message(
        raw_message="Những người đó là ai",
        user=user,
        conversation_id=conv_id,
    )
    reply2 = res2["reply"]

    assert "nhân sự" in reply2.lower()
    # Must list borrowers from the conflicting requests
    assert "Dev User" in reply2 or "Tran Thi B" in reply2 or "Manager" in reply2

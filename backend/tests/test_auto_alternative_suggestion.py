"""Tests for Automatic In-Stock Alternative Equipment Suggestion on Out-of-Stock Borrow/Query."""
from __future__ import annotations

import pytest
from app.agent.orchestrator import AgentOrchestrator
from app.agent.tools import AgentTools
from app.auth.session import SessionData
from app.core.config import settings
from app.repositories.excel_equipment import ExcelEquipmentRepository
from app.repositories.excel_request import ExcelRequestRepository


@pytest.fixture
def agent_setup():
    excel_path = settings.resolved_excel_path
    eq_repo = ExcelEquipmentRepository(str(excel_path))
    req_repo = ExcelRequestRepository(str(excel_path))
    tools = AgentTools(eq_repo, req_repo)
    orchestrator = AgentOrchestrator(tools)
    user = SessionData(
        user_email="dev.engineer@company.com",
        user_name="Dev Engineer",
        user_oid="eng-456",
        role="USER",
        is_active=True,
    )
    return orchestrator, tools, user


def test_auto_alternative_on_out_of_stock_borrow(agent_setup):
    """When a user asks to borrow equipment with 0 stock (e.g. TU2-007 Wheelspeed sensor for project ADAS),
    the assistant must detect out-of-stock condition and proactively suggest in-stock functional alternatives
    (e.g. EBS-032 WSS Continental with 25 in stock)."""
    orchestrator, tools, user = agent_setup

    res = orchestrator.process_message(
        raw_message="Tôi muốn mượn thiết bị Wheelspeed sensor TU2-007 cho dự án ADAS Mini",
        user=user,
        conversation_id="conv-alt-borrow-test",
    )

    reply = res["reply"]
    action = res.get("action")

    # 1. Notifies that the requested equipment is out of stock
    assert "TU2-007" in reply
    assert "hết hàng" in reply.lower() or "tồn kho: 0" in reply.lower()

    # 2. Automatically suggests in-stock functional alternative
    assert "Gợi ý thiết bị thay thế" in reply or "thiết bị thay thế có sẵn" in reply
    assert "EBS-032" in reply
    assert "WSS Continental" in reply
    assert "25" in reply  # Stock count

    # 3. Action is preserved for review
    assert action is not None
    assert action.get("type") == "show_borrow_form"


def test_seamless_switch_to_suggested_alternative(agent_setup):
    """When the user chooses to switch to the recommended alternative,
    the assistant opens the new borrow form with the alternative equipment and preserved project."""
    orchestrator, tools, user = agent_setup
    conv_id = "conv-switch-alt-test"

    # Turn 1: Ask for out-of-stock item
    res1 = orchestrator.process_message(
        raw_message="Tôi muốn mượn thiết bị Wheelspeed sensor TU2-007 cho dự án ADAS Mini",
        user=user,
        conversation_id=conv_id,
    )
    assert "EBS-032" in res1["reply"]

    # Turn 2: Switch to suggested alternative
    res2 = orchestrator.process_message(
        raw_message="Mượn EBS-032 cho dự án ADAS Mini",
        user=user,
        conversation_id=conv_id,
    )
    reply2 = res2["reply"]
    action2 = res2.get("action")

    assert "EBS-032" in reply2
    assert "WSS Continental" in reply2
    assert action2 is not None
    assert action2.get("type") == "show_borrow_form"
    assert action2.get("prefill", {}).get("equipment_id") == "EBS-032"
    assert action2.get("prefill", {}).get("project") == "ADAS" or "ADAS" in action2.get("prefill", {}).get("project", "")


def test_no_ambiguous_dump_when_name_and_id_combined(agent_setup):
    """Verify that when a user mentions both the full name and ID (e.g. 'Wheelspeed sensor TU2-007'),
    the assistant does NOT dump 21 ambiguous items but directly identifies TU2-007 and suggests alternatives."""
    orchestrator, tools, user = agent_setup

    res = orchestrator.process_message(
        raw_message="Tôi muốn mượn thiết bị Wheelspeed sensor TU2-007 cho dự án ADAS Mini",
        user=user,
        conversation_id="conv-disambiguate-test",
    )
    reply = res["reply"]

    # Must NOT ask the user to pick from a list of 21 items
    assert "Tôi tìm thấy 21 thiết bị" not in reply
    assert "Vui lòng chọn thiết bị bằng cách nhắn" not in reply

    # Must directly identify TU2-007 and offer EBS-032 alternative
    assert "TU2-007" in reply
    assert "EBS-032" in reply
    assert "WSS Continental" in reply

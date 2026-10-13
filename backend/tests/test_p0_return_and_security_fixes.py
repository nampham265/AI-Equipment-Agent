"""Comprehensive regression tests for P0 Return, RBAC, Retrieval, and Availability fixes."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.agent.models import ConversationState, ExtractedConstraints, IntentType
from app.agent.normalizer import extract_borrow_fields, normalize_return_condition
from app.agent.orchestrator import AgentOrchestrator
from app.agent.router import query_router
from app.agent.state import state_manager
from app.agent.tools import AgentTools
from app.auth.session import SessionData
from app.core.config import settings
from app.models.request import RequestModel
from app.repositories.excel_equipment import ExcelEquipmentRepository
from app.repositories.excel_request import ExcelRequestRepository
from app.repositories.excel_user import ExcelUserRepository
from app.schemas.requests import ReturnCondition
from app.services.approval_service import ApprovalService


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


@pytest.fixture
def test_users():
    regular_user = SessionData(
        user_email="regular.user@example.com",
        user_name="Nguyễn Văn A",
        user_oid="oid-user-1",
        is_manager=False,
        is_admin=False,
    )
    nam_pham_user = SessionData(
        user_email="nam.pham@example.com",
        user_name="Nam Phạm",
        user_oid="oid-user-2",
        is_manager=False,
        is_admin=False,
    )
    manager_user = SessionData(
        user_email="manager@example.com",
        user_name="Quản Lý Kho",
        user_oid="oid-mgr-1",
        is_manager=True,
        is_admin=False,
    )
    return {
        "regular": regular_user,
        "nam_pham": nam_pham_user,
        "manager": manager_user,
    }


def test_normalize_return_condition_mappings():
    """Verify natural Vietnamese conditions map accurately to the 6 official ReturnCondition enums."""
    assert normalize_return_condition("thiết bị còn nguyên trạng như khi nhận") == ReturnCondition.AS_RECEIVED.value
    assert normalize_return_condition("máy còn nguyên vẹn, xài tốt") == ReturnCondition.AS_RECEIVED.value
    assert normalize_return_condition("có hao mòn nhẹ nhưng dùng bình thường") == ReturnCondition.MINOR_WEAR.value
    assert normalize_return_condition("bị trầy xước nhẹ ở vỏ") == ReturnCondition.MINOR_WEAR.value
    assert normalize_return_condition("thiết bị hư hỏng nhẹ ở nút bấm") == ReturnCondition.MINOR_DAMAGE.value
    assert normalize_return_condition("hư hỏng nặng không lên nguồn") == ReturnCondition.MAJOR_DAMAGE.value
    assert normalize_return_condition("đã sửa chữa khắc phục xong") == ReturnCondition.REPAIRED.value
    assert normalize_return_condition("cần kiểm tra thêm trước khi cất kho") == ReturnCondition.NEEDS_INSPECTION.value


def test_ordinal_not_extracted_as_borrow_or_return_quantity():
    """'cái thứ 1' or 'đơn thứ 2' must not be extracted as quantity 1 or 2."""
    fields1 = extract_borrow_fields("Tôi muốn trả cái thứ 1")
    assert fields1.get("quantity") is None

    fields2 = extract_borrow_fields("Tôi muốn trả cái thứ 2 với số lượng cả 2 cái")
    assert fields2.get("quantity") == 2

    fields3 = extract_borrow_fields("Đổi thành 1 cái")
    assert fields3.get("quantity") == 1


def test_return_flow_ordinal_default_quantity_and_draft_update(agent_system, test_users):
    """P0 Return Flow:
    1. 'Tôi muốn trả cái thứ 1' selects 1st item, default quantity = loan.quantity (2, not 1).
    2. 'Mình muốn trả cả 2 cái' updates existing draft to 2, keeps form open, doesn't re-list all loans.
    3. 'Đổi thành 1 cái' updates draft quantity to 1.
    """
    orch = agent_system["orchestrator"]
    user = test_users["nam_pham"]
    conv_id = "test_return_conv_p0"

    # Mock active loans for user
    loan1 = RequestModel(
        id=71,
        requester_name="Nam Phạm",
        requester_email=user.user_email,
        project="Alpha",
        equipment_id="TU1-001",
        quantity=2,
        needed_from="2026-03-01",
        needed_to="2026-03-10",
        purpose="Test",
        status="Borrowed",
        created_at="2026-03-01T00:00:00Z",
        modified_at="2026-03-01T00:00:00Z",
    )
    loan1.equipment_name = "Conn header SMD 24pos 3mm female"

    loan2 = RequestModel(
        id=72,
        requester_name="Nam Phạm",
        requester_email=user.user_email,
        project="Beta",
        equipment_id="TU1-002",
        quantity=3,
        needed_from="2026-03-05",
        needed_to="2026-03-15",
        purpose="Test",
        status="Borrowed",
        created_at="2026-03-05T00:00:00Z",
        modified_at="2026-03-05T00:00:00Z",
    )
    loan2.equipment_name = "CAN Interface Module"

    orch.tools.get_active_loans_for_user = MagicMock(return_value=[loan1, loan2])

    # Turn 1: Initial list
    res1 = orch.process_message("Tôi muốn trả đồ", user, conv_id)
    assert res1.get("action") is None  # Multiple loans -> selection list
    state1 = state_manager.get_state(user.user_email, conv_id)
    assert state1.pending_action == "return"

    # Turn 2: Select ordinal 1
    res2 = orch.process_message("Tôi muốn trả cái thứ 1", user, conv_id)
    act2 = res2.get("action")
    assert act2 is not None
    assert act2["type"] == "show_return_form"
    assert act2["prefill"]["equipment_id"] == "TU1-001"
    # Crucial assertion: default quantity must be loan1.quantity (2), NOT 1!
    assert act2["prefill"]["quantity"] == 2
    assert act2["prefill"]["max_quantity"] == 2

    # Turn 3: User says "Mình muốn trả cả 2 cái"
    res3 = orch.process_message("Mình muốn trả cả 2 cái", user, conv_id)
    act3 = res3.get("action")
    assert act3 is not None
    assert act3["type"] == "show_return_form"
    assert act3["prefill"]["equipment_id"] == "TU1-001"
    assert act3["prefill"]["quantity"] == 2
    assert "cập nhật số lượng hoàn trả thành **2** cái" in res3["reply"]

    # Turn 4: User adjusts to partial return: "Đổi thành 1 cái"
    res4 = orch.process_message("Đổi thành 1 cái", user, conv_id)
    act4 = res4.get("action")
    assert act4 is not None
    assert act4["type"] == "show_return_form"
    assert act4["prefill"]["quantity"] == 1
    assert "cập nhật số lượng hoàn trả thành **1** cái" in res4["reply"]


def test_partial_return_approval_service():
    """ApprovalService.mark_returned must support partial returns when quantity < loan.quantity."""
    mock_repo = MagicMock()
    mock_notify = MagicMock()
    service = ApprovalService(mock_repo, mock_notify)

    loan = RequestModel(
        id=10,
        requester_name="Nam Phạm",
        requester_email="nam.pham@example.com",
        project="Delta",
        equipment_id="TU1-001",
        quantity=5,
        needed_from="2026-03-01",
        needed_to="2026-03-10",
        purpose="Test",
        priority_level="Medium",
        priority_reason="Test priority reason",
        status="Borrowed",
        created_at="2026-03-01T00:00:00Z",
        modified_at="2026-03-01T00:00:00Z",
    )
    mock_repo.get_by_id.return_value = loan
    mock_repo.update.side_effect = lambda r: r

    # Return 2 out of 5
    result = service.mark_returned(
        request_id=10,
        return_condition=ReturnCondition.MINOR_WEAR.value,
        return_condition_note="Hao mòn nhẹ đầu cắm",
        actor_email="nam.pham@example.com",
        quantity=2,
    )

    # Verifications
    # 1. A new returned record was created with quantity 2
    mock_repo.create.assert_called_once()
    created_call_arg = mock_repo.create.call_args[0][0]
    assert created_call_arg.quantity == 2
    assert created_call_arg.status == "Returned"
    assert created_call_arg.return_condition == ReturnCondition.MINOR_WEAR.value
    assert created_call_arg.return_condition_note == "Hao mòn nhẹ đầu cắm"

    # 2. Original loan quantity was updated to 3 and remains Borrowed
    assert loan.quantity == 3
    assert loan.status == "Borrowed"


def test_rbac_security_regular_user_cannot_view_others_loans(agent_system, test_users):
    """P0 Security: Regular user asking 'Còn của Nam Phạm thì sao' must be refused by RBAC."""
    orch = agent_system["orchestrator"]
    regular_user = test_users["regular"]  # Nguyễn Văn A
    conv_id = "test_rbac_conv"

    # Regular user asks about their own requests first
    orch.process_message("Hiện mình đang mượn mấy thiết bị", regular_user, conv_id)

    # Regular user asks about Nam Pham
    res2 = orch.process_message("Còn của Nam Phạm thì sao", regular_user, conv_id)
    reply = res2["reply"]
    assert "Bạn chỉ có quyền xem các thiết bị do chính mình mượn" in reply
    assert "quản lý" in reply.lower()


def test_manager_pronoun_context_overdue_loans(agent_system, test_users):
    """P0 Manager chain:
    1. Manager queries Nam Phạm loans -> state.active_person set to 'Nam Phạm'.
    2. Manager asks 'Các thiết bị bạn đó mượn có quá hạn không?' -> resolves 'bạn đó' to Nam Phạm and filters overdue items.
    """
    orch = agent_system["orchestrator"]
    manager = test_users["manager"]
    conv_id = "test_manager_chain_conv"

    # Turn 1: Manager asks about active loans of Nam Pham
    res1 = orch.process_message("Còn của Nam Phạm thì sao", manager, conv_id)
    state = state_manager.get_state(manager.user_email, conv_id)
    assert state.active_person == "Nam Phạm"

    # Mock overdue items: 1 for Nam Phạm, 1 for someone else
    overdue_nam = {
        "RequestID": "REQ-000081",
        "id": 81,
        "borrower": "Nam Phạm",
        "borrower_email": "nam.pham@example.com",
        "equipment_id": "TU1-001",
        "equipment_name": "Conn header SMD 24pos 3mm female",
        "project": "Alpha",
        "needed_from": "2026-01-01",
        "needed_to": "2026-01-10",
        "days_overdue": 30,
        "Quantity": 2,
    }
    overdue_other = {
        "RequestID": "REQ-000099",
        "id": 99,
        "borrower": "Other Person",
        "borrower_email": "other@example.com",
        "equipment_id": "TU2-001",
        "equipment_name": "Cable",
        "project": "Gamma",
        "needed_from": "2026-01-01",
        "needed_to": "2026-01-10",
        "days_overdue": 30,
        "Quantity": 1,
    }
    orch.tools.get_overdue_loans = MagicMock(return_value=[overdue_nam, overdue_other])

    # Turn 2: Manager asks about overdue items using pronoun 'bạn đó'
    res2 = orch.process_message("Các thiết bị bạn đó mượn có quá hạn không?", manager, conv_id)
    reply2 = res2["reply"]
    assert "REQ-000081" in reply2
    assert "REQ-000099" not in reply2  # Other person's overdue loan filtered out!


def test_banana_jumper_color_filtering(agent_system, test_users):
    """P1 Banana jumper:
    'Tìm Banana jumper màu đỏ' must return ONLY TU1-010.
    'Tìm Banana jumper màu đen' must return ONLY TU1-011.
    Must never match PLA spool EBS-011 (đỏ) or Emergency button TU2-015 (đỏ).
    """
    orch = agent_system["orchestrator"]
    user = test_users["regular"]

    res_red = orch.process_message("Tìm Banana jumper màu đỏ", user, "conv_jumper_red")
    reply_red = res_red["reply"]
    assert "TU1-010" in reply_red
    assert "TU1-011" not in reply_red
    assert "EBS-011" not in reply_red
    assert "TU2-015" not in reply_red

    res_black = orch.process_message("Tìm Banana jumper màu đen", user, "conv_jumper_black")
    reply_black = res_black["reply"]
    assert "TU1-011" in reply_black
    assert "TU1-010" not in reply_black
    assert "EBS-011" not in reply_black


def test_availability_no_stale_context_bleed(agent_system, test_users):
    """P1: 'Conn header SMD 24pos 3mm female nếu mượn 30 cái thì sao?'
    Must resolve directly to TU1-001, never bleed TU2-007 from stale context!
    """
    orch = agent_system["orchestrator"]
    user = test_users["regular"]
    conv_id = "conv_no_bleed"

    # Pre-seed state with stale TU2-007
    state = state_manager.get_state(user.user_email, conv_id)
    state.active_equipment = {
        "EquipmentID": "TU2-007",
        "EquipmentName": "Stale Equipment",
        "Quantity": 10,
    }
    state.active_equipment_ids = ["TU2-007"]
    state_manager.save_state(state)

    # User asks about Conn header with 30 items
    msg = "Conn header SMD 24pos 3mm female nếu mượn 30 cái thì sao?"
    res = orch.process_message(msg, user, conv_id)
    reply = res["reply"]

    # Must resolve TU1-001
    assert "TU1-001" in reply
    assert "TU2-007" not in reply
    # State active_equipment must now be TU1-001
    state_after = state_manager.get_state(user.user_email, conv_id)
    assert state_after.active_equipment.get("EquipmentID") == "TU1-001"


def test_distinct_connector_type_count(agent_system, test_users):
    """P1: 'Kho hiện có bao nhiêu loại connector?' must return concise count, not 1-15 dump."""
    orch = agent_system["orchestrator"]
    user = test_users["regular"]

    msg = "Kho hiện có bao nhiêu loại connector?"
    res = orch.process_message(msg, user, "conv_conn_count")
    reply = res["reply"]
    assert "loại" in reply
    assert "connector" in reply.lower() or "thiết bị" in reply.lower()
    # Must be concise count summary, not paginated 1-15 table header
    assert "| Mã thiết bị |" not in reply

"""Regression tests for reported bugs in AI Equipment Agent V1.

Tests:
1. Equipment switch availability check: asking for 'Conn header SMD 24pos 3mm female'
   after interacting with Wheelspeed sensor (TU2-007) does NOT get hijacked by TU2-007.
2. Instant availability explanation: calculates real stock availability without
   returning the canned refusal ('chưa có đủ dữ liệu mượn/trả...').
3. Person follow-up for overdue loans: 'Hải Nam là đang mượn những đơn nào quá hạn chưa trả'
   and 'Nam Phạm là đang trễ hạn trả những thiết bị nào' return the 5 overdue requests.
4. Person follow-up for active loans: 'Hải Nam là đang mượn những thiết bị nào chưa trả'
   lists the borrowed loans for that person.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agent.models import IntentType
from app.agent.numeric import NumericExplanation
from app.agent.state import state_manager
from app.auth.session import SessionData
from app.core.config import settings
from app.main import app


@pytest.fixture
def api_client():
    client = TestClient(app)
    # Login as Nam Pham
    client.post("/auth/dev-login", json={"email": "nampham.31231023820@st.ueh.edu.vn"})
    return client


def test_numeric_explanation_instant_availability():
    """When has_date_range is False, NumericExplanation calculates instant stock availability."""
    # Sufficiency: 37 in warehouse, 10 requested, 23 available -> enough
    res = NumericExplanation.explain_sufficiency(
        equipment_id="TU1-001",
        equipment_name="Conn header SMD 24pos 3mm female",
        total_quantity=37,
        available_quantity=23,
        requested_quantity=10,
        unit="cái",
        has_date_range=False,
    )
    assert "chưa có đủ dữ liệu" not in res
    assert "23 cái" in res
    assert "hoàn toàn đủ" in res
    assert "10 cái" in res

    # Shortage: 3 in stock, 5 requested -> shortage
    res_short = NumericExplanation.explain_sufficiency(
        equipment_id="TU1-001",
        equipment_name="Conn header SMD 24pos 3mm female",
        total_quantity=37,
        available_quantity=3,
        requested_quantity=5,
        unit="cái",
        has_date_range=False,
    )
    assert "chưa có đủ dữ liệu" not in res_short
    assert "không đủ" in res_short
    assert "thiếu 2 cái" in res_short


def test_equipment_switch_availability_not_hijacked(api_client):
    """Chatting about Conn header after Wheelspeed sensor resolves to TU1-001, not TU2-007."""
    cid = "conv-switch-test"
    # Seed state with TU2-007
    user_email = "nampham.31231023820@st.ueh.edu.vn"
    state = state_manager.get_state(user_email, cid)
    state.active_equipment = {
        "EquipmentID": "TU2-007",
        "EquipmentName": "Wheelspeed sensor",
        "Quantity": 0,
        "Location": "Tủ 2",
    }
    state.active_equipment_ids = ["TU2-007"]

    # Now ask about Conn header SMD
    res = api_client.post(
        "/api/agent/message",
        json={
            "message": "Conn header SMD 24pos 3mm female có đang được ai sử dụng không, và hiện có còn dư trong kho để cho mình mượn tầm 10 cái không",
            "conversation_id": cid,
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]
    trace = data.get("trace", {})

    # Must NOT mention Wheelspeed sensor or TU2-007
    assert "TU2-007" not in reply
    assert "Wheelspeed" not in reply

    # Must resolve TU1-001
    assert "TU1-001" in reply
    assert "Conn header SMD 24pos 3mm female" in reply

    # Must NOT have canned refusal
    assert "chưa có đủ dữ liệu mượn/trả" not in reply

    # Must mention stock and usage
    assert "Tủ 1" in reply
    assert "37 cái" in reply
    assert "10 cái" in reply
    assert "đủ" in reply.lower()


def test_overdue_loans_by_person_hai_nam(api_client):
    """Asking for overdue loans for Hải Nam returns the 5 overdue requests of Phạm Ngọc Hải Nam."""
    cid = "conv-overdue-hai-nam"
    user_email = "nampham.31231023820@st.ueh.edu.vn"
    state = state_manager.get_state(user_email, cid)
    state.last_result_type = "overdue_borrowers"
    state.last_intent = IntentType.OVERDUE_BORROWERS

    res = api_client.post(
        "/api/agent/message",
        json={
            "message": "Hải Nam là đang mượn những đơn nào quá hạn chưa trả",
            "conversation_id": cid,
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]

    # Must NOT return generic zero-loan message
    assert "không có thiết bị nào" not in reply
    assert "chưa ghi nhận" not in reply

    # Must find the 5 overdue items
    assert "5" in reply
    assert "Phạm Ngọc Hải Nam" in reply
    assert "TU1-001" in reply
    assert "TU1-008" in reply
    assert "TU1-017" in reply
    assert "TU1-013" in reply
    assert "TU1-023" in reply


def test_overdue_loans_by_person_nam_pham(api_client):
    """Asking for overdue loans for Nam Phạm also matches Phạm Ngọc Hải Nam's 5 overdue requests."""
    cid = "conv-overdue-nam-pham"
    user_email = "nampham.31231023820@st.ueh.edu.vn"
    state = state_manager.get_state(user_email, cid)
    state.last_result_type = "overdue_borrowers"
    state.last_intent = IntentType.OVERDUE_BORROWERS

    res = api_client.post(
        "/api/agent/message",
        json={
            "message": "Nam Phạm là đang trễ hạn trả những thiết bị nào",
            "conversation_id": cid,
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]

    assert "không có thiết bị nào" not in reply
    assert "5" in reply
    assert "Phạm Ngọc Hải Nam" in reply
    assert "TU1-001" in reply
    assert "TU1-008" in reply
    assert "TU1-017" in reply
    assert "TU1-013" in reply
    assert "TU1-023" in reply


def test_active_loans_by_person_chua_tra(api_client):
    """Asking 'Hải Nam là đang mượn những thiết bị nào chưa trả' returns the borrowed items."""
    cid = "conv-borrowed-chua-tra"
    user_email = "nampham.31231023820@st.ueh.edu.vn"
    state = state_manager.get_state(user_email, cid)
    state.last_result_type = "overdue_borrowers"
    state.last_intent = IntentType.OVERDUE_BORROWERS

    res = api_client.post(
        "/api/agent/message",
        json={
            "message": "Hải Nam là đang mượn những thiết bị nào chưa trả",
            "conversation_id": cid,
        },
    )
    assert res.status_code == 200
    data = res.json()
    reply = data["reply"]

    # Must NOT claim user has no loans
    assert "chưa ghi nhận thiết bị nào đang được bạn mượn" not in reply
    assert "Phạm Ngọc Hải Nam" in reply or "TU1-001" in reply

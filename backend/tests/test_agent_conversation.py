"""Tests for conversational context, precise field queries, and pagination in chat agent."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth.session import SessionData, set_session


@pytest.fixture
def auth_client():
    client = TestClient(app)
    # Perform dev-login as admin/user
    res = client.post("/auth/dev-login", json={"email": "nampham.31231023820@st.ueh.edu.vn"})
    assert res.status_code == 200
    return client


def test_location_query_precise_answer(auth_client):
    """Test asking for location returns a concise location without full dump."""
    res = auth_client.post(
        "/api/agent/message",
        json={
            "message": "CSW-005: ECU ABS 10.3ME hiện tại đang nằm ở đâu",
            "conversation_history": [],
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "tủ CSW" in data["reply"]
    assert "📍" in data["reply"]
    # Should NOT dump the 500-char long description
    assert "Khối điều khiển ECU hệ thống phanh ABS Thế hệ 10 cao cấp" not in data["reply"]


def test_followup_clarification_inherits_count_intent(auth_client):
    """Test when bot gives options, follow-up short message inherits previous count query."""
    # Step 1: User asks count of ABS
    res1 = auth_client.post(
        "/api/agent/message",
        json={
            "message": "Hiện tại có bao nhiêu cục ABS",
            "conversation_history": [],
        },
    )
    assert res1.status_code == 200
    reply1 = res1.json()["reply"]
    assert "ECU ABS 10.3MP" in reply1

    # Step 2: User responds "10.3MP"
    res2 = auth_client.post(
        "/api/agent/message",
        json={
            "message": "10.3MP",
            "conversation_history": [
                {"role": "user", "content": "Hiện tại có bao nhiêu cục ABS"},
                {"role": "assistant", "content": reply1},
            ],
        },
    )
    assert res2.status_code == 200
    reply2 = res2.json()["reply"]
    # Bot should resolve to CSW-002: ECU ABS 10.3MP and report quantity
    assert "CSW-002" in reply2
    assert "5 cái" in reply2 or "5" in reply2
    assert "tủ CSW" in reply2


def test_pagination_xem_tiep(auth_client):
    """Test 'mình muốn xem tiếp' returns page 2 of equipment list."""
    # Step 1: List all
    res1 = auth_client.post(
        "/api/agent/message",
        json={
            "message": "Cho mình xem các danh sách trong kho",
            "conversation_history": [],
        },
    )
    assert res1.status_code == 200
    reply1 = res1.json()["reply"]
    assert "TU1-001" in reply1

    # Step 2: User asks "Mình muốn xem tiếp"
    res2 = auth_client.post(
        "/api/agent/message",
        json={
            "message": "Mình muốn xem tiếp",
            "conversation_history": [
                {"role": "user", "content": "Cho mình xem các danh sách trong kho"},
                {"role": "assistant", "content": reply1},
            ],
        },
    )
    assert res2.status_code == 200
    reply2 = res2.json()["reply"]
    # Should show items from 16 onwards (TU1-016), NOT restart at TU1-001
    assert "TU1-016" in reply2
    assert "từ 16 đến 30" in reply2

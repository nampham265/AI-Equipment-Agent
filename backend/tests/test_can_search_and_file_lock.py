"""Tests for CAN module retrieval precision and Excel file lock safety."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.agent.models import ExtractedConstraints
from app.agent.retrieval import HybridRetrievalService, _sanitize_technical_text
from app.agent.orchestrator import AgentOrchestrator
from app.agent.tools import AgentTools
from app.auth.session import SessionData
from app.core.config import settings
from app.main import app
from app.repositories.excel_equipment import ExcelEquipmentRepository
from app.repositories.excel_request import ExcelRequestRepository, ExcelFileLockedError


@pytest.fixture
def repos():
    excel_path = settings.resolved_excel_path
    eq_repo = ExcelEquipmentRepository(str(excel_path))
    req_repo = ExcelRequestRepository(str(excel_path))
    return eq_repo, req_repo


def test_can_prose_sanitization():
    """Verify Vietnamese prose with 'can' is stripped to prevent collision with CAN protocol."""
    text1 = "xử lý các tín hiệu I/O đơn giản mà không cần can thiệp qua máy tính chính."
    clean1 = _sanitize_technical_text(text1)
    assert "can thiệp" not in clean1
    assert "can" not in clean1.lower()

    text2 = "Module giao tiếp CAN Bus phiên bản B gắn cho Raspberry Pi Pico."
    clean2 = _sanitize_technical_text(text2)
    assert "can bus" in clean2.lower()

    text3 = "không can dự hoặc ngăn can các tiến trình khác"
    clean3 = _sanitize_technical_text(text3)
    assert "can" not in clean3.lower()


def test_can_module_retrieval_excludes_microlc(repos):
    """Verify that 'module CAN' search returns real CAN boards and strictly excludes MicroLC."""
    eq_repo, _ = repos
    retrieval = HybridRetrievalService(eq_repo)

    constraints = ExtractedConstraints(
        category="module",
        keywords=["CAN", "module CAN"],
    )
    results = retrieval.search_equipment(constraints, query_text="Trong kho có module CAN nào không?")
    result_ids = [r.equipment_id for r in results]

    # Must contain legitimate CAN modules
    assert "EBS-040" in result_ids  # Pico Can B
    assert "TU2-002" in result_ids  # HS+ Interface (Kênh CAN High-Speed số 1)

    # Must strictly EXCLUDE MicroLC (which only had 'can thiệp' in prose)
    assert "TU2-005" not in result_ids

    # Must not match random boards without CAN (e.g. LM2596, ESP32)
    assert "EBS-042" not in result_ids
    assert "EBS-045" not in result_ids


def test_orchestrator_can_module_chat_reply(repos):
    """Verify end-to-end orchestrator reply for 'Trong kho có module CAN nào không?'."""
    eq_repo, req_repo = repos
    tools = AgentTools(eq_repo, req_repo)
    orch = AgentOrchestrator(tools=tools)

    user = SessionData(
        user_email="nampham.31231023820@st.ueh.edu.vn",
        user_name="Nam",
        role="USER",
        is_active=True,
    )

    res = orch.process_message("Trong kho có module CAN nào không?", user=user, conversation_id="test-can-conv")
    reply = res.get("reply", "")

    # MicroLC should not be in the reply
    assert "MicroLC" not in reply
    assert "TU2-005" not in reply

    # Legitimate items should be present
    assert "Pico Can B" in reply or "EBS-040" in reply


def test_excel_file_locked_error_returns_423():
    """Verify that when Excel workbook is locked, POST /api/requests returns 423 with clear message."""
    client = TestClient(app)

    # Login via dev-login
    login_res = client.post("/auth/dev-login", json={"email": "nampham.31231023820@st.ueh.edu.vn"})
    assert login_res.status_code == 200

    payload = {
        "project": "Minilab",
        "equipment_id": "TU1-001",
        "quantity": 5,
        "needed_from": "2026-10-13",
        "needed_to": "2026-10-14",
        "purpose": "Test borrow lock",
    }

    # Simulate ExcelFileLockedError from repository
    with patch("app.repositories.excel_request.ExcelRequestRepository.create") as mock_create:
        mock_create.side_effect = ExcelFileLockedError(
            "Tệp dữ liệu Excel 'equipment_agent.xlsx' hiện đang bị khóa hoặc được mở bởi ứng dụng khác (ví dụ: Microsoft Excel). "
            "Vui lòng lưu và đóng file Excel trên máy tính rồi thử lại."
        )

        res = client.post("/api/requests", json=payload)
        assert res.status_code == 423
        data = res.json()
        assert "đang bị khóa" in data["detail"]
        assert "Microsoft Excel" in data["detail"]

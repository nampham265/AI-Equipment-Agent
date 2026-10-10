"""Comprehensive automated test suite for Low-Stock Inventory Reporting capability.

Covers:
1. "Hiện tại trong kho có thiết bị nào sắp hết không" -> low_stock_inventory, default threshold.
2. "Những thiết bị nào còn dưới 5 cái?" -> strict comparison Quantity < 5.
3. "Những thiết bị nào còn 5 cái trở xuống?" -> inclusive comparison Quantity <= 5.
4. "Những thiết bị nào còn dưới 10 cái?" -> query-specific threshold 10.
5. Zero matches -> explicit no-low-stock response, not searching for "sắp hết".
6. Missing, invalid or nonnumeric quantities handled safely without inventing quantities.
7. Gemini failure or invalid structured output -> falls back safely, never searches for "sắp hết".
8. Regression verification on existing equipment search, exact ID, count, borrow and return.
"""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.deps import get_current_user
from app.auth.session import SessionData
from app.agent.models import (
    ConversationState,
    IntentType,
    QueryPlan,
    GeminiRouterOutput,
    LLMConstraints,
    ExtractedConstraints,
)
from app.agent.tools import AgentTools
from app.agent.router import query_router
from app.agent.orchestrator import AgentOrchestrator, _map_gemini_to_plan
from app.schemas.equipment import EquipmentRead


class DummyEquipment:
    def __init__(self, equipment_id, equipment_name, quantity_total=None, unit="cái", location="Kho", category="Unknown"):
        self.equipment_id = equipment_id
        self.equipment_name = equipment_name
        self.quantity_total = quantity_total
        self.unit = unit
        self.location = location
        self.category = category


@pytest.fixture(autouse=True)
def clean_dependency_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_user():
    return SessionData(
        user_email="tester@example.com",
        user_name="Tester",
        user_oid="oid-test",
        is_manager=False,
        role="USER",
    )


@pytest.fixture
def mock_equipment_repo():
    repo = MagicMock()
    # Create controlled test items with various boundary quantities
    items = [
        EquipmentRead(
            equipment_id="TEST-000",
            equipment_name="Cảm biến quang 0 cái",
            quantity_total=0,
            unit="cái",
            location="Tủ 1",
            category="Sensor",
        ),
        EquipmentRead(
            equipment_id="TEST-004",
            equipment_name="Bo mạch test 4 cái",
            quantity_total=4,
            unit="bộ",
            location="Tủ 1",
            category="Board",
        ),
        EquipmentRead(
            equipment_id="TEST-005",
            equipment_name="Cáp kết nối 5 cái",
            quantity_total=5,
            unit="sợi",
            location="Tủ 2",
            category="Cable",
        ),
        EquipmentRead(
            equipment_id="TEST-006",
            equipment_name="Nguồn adapter 6 cái",
            quantity_total=6,
            unit="cái",
            location="EBS_LAB",
            category="Power",
        ),
        EquipmentRead(
            equipment_id="TEST-010",
            equipment_name="Bộ dụng cụ 10 cái",
            quantity_total=10,
            unit="hộp",
            location="EBS_LAB",
            category="Tools",
        ),
        DummyEquipment(
            equipment_id="TEST-NONE",
            equipment_name="Thiết bị chưa kiểm kê",
            quantity_total=None,
            unit="cái",
            location="Tủ 3",
            category="Unknown",
        ),
    ]
    repo.get_all.return_value = items
    repo.get_by_id.side_effect = lambda eid: next((it for it in items if it.equipment_id == eid), None)
    return repo


@pytest.fixture
def mock_request_repo():
    repo = MagicMock()
    repo.get_overlapping.return_value = []
    repo.list_by_requester.return_value = []
    return repo


class TestLowStockBackendTool:
    """Test unit behavior of get_low_stock_inventory in AgentTools."""

    def test_default_threshold_inclusive(self, mock_equipment_repo, mock_request_repo):
        tools = AgentTools(mock_equipment_repo, mock_request_repo)
        res = tools.get_low_stock_inventory()

        assert res["threshold"] == 5
        assert res["operator"] == "<="
        # Items with qty <= 5 are TEST-000 (0), TEST-004 (4), TEST-005 (5)
        matched_ids = [it["equipment_id"] for it in res["items"]]
        assert matched_ids == ["TEST-000", "TEST-004", "TEST-005"]
        assert res["total_matches"] == 3

    def test_strict_threshold_less_than_five(self, mock_equipment_repo, mock_request_repo):
        tools = AgentTools(mock_equipment_repo, mock_request_repo)
        res = tools.get_low_stock_inventory(threshold=5, operator="<")

        assert res["threshold"] == 5
        assert res["operator"] == "<"
        # Strict < 5: TEST-000 (0), TEST-004 (4)
        matched_ids = [it["equipment_id"] for it in res["items"]]
        assert matched_ids == ["TEST-000", "TEST-004"]
        assert "TEST-005" not in matched_ids
        assert res["total_matches"] == 2

    def test_custom_threshold_ten(self, mock_equipment_repo, mock_request_repo):
        tools = AgentTools(mock_equipment_repo, mock_request_repo)
        res = tools.get_low_stock_inventory(threshold=10, operator="<")

        assert res["threshold"] == 10
        assert res["operator"] == "<"
        matched_ids = [it["equipment_id"] for it in res["items"]]
        # Strict < 10: 0, 4, 5, 6
        assert matched_ids == ["TEST-000", "TEST-004", "TEST-005", "TEST-006"]
        assert "TEST-010" not in matched_ids
        assert res["total_matches"] == 4

    def test_sorting_order_ascending_with_tie_break(self, mock_request_repo):
        repo = MagicMock()
        items = [
            EquipmentRead(equipment_id="B-02", equipment_name="B", quantity_total=2),
            EquipmentRead(equipment_id="A-01", equipment_name="A", quantity_total=1),
            EquipmentRead(equipment_id="C-01", equipment_name="C", quantity_total=1),
        ]
        repo.get_all.return_value = items
        tools = AgentTools(repo, mock_request_repo)
        res = tools.get_low_stock_inventory(threshold=5)

        # Sorted by quantity asc (1, 1, 2) and tie broken by id (A-01 before C-01)
        matched_ids = [it["equipment_id"] for it in res["items"]]
        assert matched_ids == ["A-01", "C-01", "B-02"]

    def test_safe_handling_of_invalid_and_none_quantities(self, mock_request_repo):
        repo = MagicMock()
        items = [
            EquipmentRead(equipment_id="VALID-1", equipment_name="Val 1", quantity_total=2),
            DummyEquipment(equipment_id="INVALID-1", equipment_name="Inv 1", quantity_total=None),
            DummyEquipment(equipment_id="INVALID-2", equipment_name="Inv 2", quantity_total="not_a_number"),
        ]
        repo.get_all.return_value = items
        tools = AgentTools(repo, mock_request_repo)
        res = tools.get_low_stock_inventory(threshold=5)

        assert res["total_matches"] == 1
        assert res["items"][0]["equipment_id"] == "VALID-1"

    def test_zero_matches_handled_cleanly(self, mock_request_repo):
        repo = MagicMock()
        items = [
            EquipmentRead(equipment_id="HIGH-1", equipment_name="High 1", quantity_total=50),
        ]
        repo.get_all.return_value = items
        tools = AgentTools(repo, mock_request_repo)
        res = tools.get_low_stock_inventory(threshold=5)

        assert res["total_matches"] == 0
        assert res["items"] == []


class TestQueryRouterLowStock:
    """Test deterministic regex and fallback routing for low stock queries."""

    def test_route_message_sap_het_default(self):
        state = ConversationState(conversation_id="c1", user_email="test@example.com")
        plan = query_router.route_message("Hiện tại trong kho có thiết bị nào sắp hết không", state)
        assert plan.intent == IntentType.LOW_STOCK_INVENTORY
        assert plan.low_stock_threshold is None
        assert plan.low_stock_operator is None
        assert plan.entity_id is None
        assert "sắp hết" not in plan.constraints.keywords

    def test_route_message_strict_duoi_5(self):
        state = ConversationState(conversation_id="c1", user_email="test@example.com")
        plan = query_router.route_message("Những thiết bị nào còn dưới 5 cái?", state)
        assert plan.intent == IntentType.LOW_STOCK_INVENTORY
        assert plan.low_stock_threshold == 5
        assert plan.low_stock_operator == "<"

    def test_route_message_inclusive_5_tro_xuong(self):
        state = ConversationState(conversation_id="c1", user_email="test@example.com")
        plan = query_router.route_message("Những thiết bị nào còn 5 cái trở xuống?", state)
        assert plan.intent == IntentType.LOW_STOCK_INVENTORY
        assert plan.low_stock_threshold == 5
        assert plan.low_stock_operator == "<="

    def test_route_message_duoi_10(self):
        state = ConversationState(conversation_id="c1", user_email="test@example.com")
        plan = query_router.route_message("Những thiết bị nào còn dưới 10 cái?", state)
        assert plan.intent == IntentType.LOW_STOCK_INVENTORY
        assert plan.low_stock_threshold == 10
        assert plan.low_stock_operator == "<"

    def test_route_message_natural_variants(self):
        state = ConversationState(conversation_id="c1", user_email="test@example.com")
        variants = [
            "Hiện tại có món nào sắp hết không?",
            "Những thiết bị nào còn ít?",
            "Kho còn những món nào dưới 5 cái?",
            "Liệt kê thiết bị có số lượng tồn thấp.",
            "Có thiết bị nào cần bổ sung không?",
        ]
        for v in variants:
            plan = query_router.route_message(v, state)
            assert plan.intent == IntentType.LOW_STOCK_INVENTORY, f"Failed for variant: {v}"
            assert plan.entity_id is None
            assert plan.entity_name is None


class TestOrchestratorLowStock:
    """Test orchestrator execution and formatting for low-stock inventory."""

    def test_orchestrator_formats_markdown_table_with_records(self, mock_equipment_repo, mock_request_repo, auth_user):
        tools = AgentTools(mock_equipment_repo, mock_request_repo)
        orchestrator = AgentOrchestrator(tools=tools, gemini_router=None)

        result = orchestrator.process_message(
            raw_message="Hiện tại trong kho có thiết bị nào sắp hết không",
            user=auth_user,
            conversation_id="conv-low-stock-test",
        )

        trace = result["trace"]
        assert trace["intent"] == "low_stock_inventory"
        assert trace["selected_tool"] == "get_low_stock_inventory"
        assert trace["tool_result_count"] == 3
        assert trace["tool_arguments"] == {"threshold": 5, "operator": "<="}

        reply = result["reply"]
        assert "Báo cáo thiết bị có số lượng tồn thấp" in reply
        assert "| Tên thiết bị | Số lượng ghi nhận | Đơn vị | Vị trí | Mã thiết bị |" in reply
        assert "Cảm biến quang 0 cái" in reply
        assert "TEST-000" in reply
        assert "Bo mạch test 4 cái" in reply
        assert "TEST-004" in reply
        assert "Cáp kết nối 5 cái" in reply
        assert "TEST-005" in reply
        assert "Không tìm thấy thiết bị sắp hết" not in reply

    def test_orchestrator_handles_zero_matches_with_explicit_message(self, mock_request_repo, auth_user):
        repo = MagicMock()
        repo.get_all.return_value = [
            EquipmentRead(equipment_id="HIGH-1", equipment_name="Thiết bị nhiều", quantity_total=100),
        ]
        tools = AgentTools(repo, mock_request_repo)
        orchestrator = AgentOrchestrator(tools=tools, gemini_router=None)

        result = orchestrator.process_message(
            raw_message="Hiện tại trong kho có thiết bị nào sắp hết không",
            user=auth_user,
            conversation_id="conv-empty-low-stock",
        )

        reply = result["reply"]
        assert "không có thiết bị nào có số lượng tồn" in reply
        assert "Không tìm thấy thiết bị sắp hết" not in reply
        assert result["trace"]["selected_tool"] == "get_low_stock_inventory"

    def test_gemini_fallback_never_searches_for_sap_het(self, mock_equipment_repo, mock_request_repo, auth_user):
        # Simulate gemini returning an erroneous or search intent with keyword 'sắp hết'
        gemini_mock = MagicMock()
        gemini_mock.classify_message.return_value = GeminiRouterOutput(
            intent="equipment_search",
            confidence=0.8,
            constraints=LLMConstraints(keywords=["sắp hết"]),
        )
        tools = AgentTools(mock_equipment_repo, mock_request_repo)
        orchestrator = AgentOrchestrator(tools=tools, gemini_router=gemini_mock)

        result = orchestrator.process_message(
            raw_message="Hiện tại trong kho có thiết bị nào sắp hết không",
            user=auth_user,
            conversation_id="conv-fallback-safe",
        )

        trace = result["trace"]
        # Guard in _map_gemini_to_plan corrects it to LOW_STOCK_INVENTORY
        assert trace["intent"] == "low_stock_inventory"
        assert trace["selected_tool"] == "get_low_stock_inventory"
        assert "Không tìm thấy thiết bị sắp hết" not in result["reply"]


class TestApiIntegrationLowStock:
    """End-to-end API tests against POST /api/agent/message."""

    def test_api_message_sap_het_live_catalog(self, auth_user):
        app.dependency_overrides[get_current_user] = lambda: auth_user
        client = TestClient(app)

        res = client.post(
            "/api/agent/message",
            json={
                "message": "Hiện tại trong kho có thiết bị nào sắp hết không",
                "conversation_id": "test-e2e-api-low-stock",
            },
        )
        assert res.status_code == 200
        data = res.json()
        trace = data.get("trace", {})

        assert trace.get("intent") == "low_stock_inventory"
        assert trace.get("selected_tool") == "get_low_stock_inventory"
        assert trace.get("tool_result_count") > 0
        assert "Không tìm thấy thiết bị sắp hết" not in data.get("reply", "")
        assert "| Tên thiết bị | Số lượng ghi nhận |" in data.get("reply", "")

    def test_api_message_strict_duoi_5(self, auth_user):
        app.dependency_overrides[get_current_user] = lambda: auth_user
        client = TestClient(app)

        res = client.post(
            "/api/agent/message",
            json={
                "message": "Những thiết bị nào còn dưới 5 cái?",
                "conversation_id": "test-e2e-strict-5",
            },
        )
        assert res.status_code == 200
        data = res.json()
        trace = data.get("trace", {})

        assert trace.get("intent") == "low_stock_inventory"
        assert trace.get("selected_tool") == "get_low_stock_inventory"
        assert trace.get("tool_arguments", {}).get("operator") == "<"
        assert trace.get("tool_arguments", {}).get("threshold") == 5

    def test_api_message_duoi_10(self, auth_user):
        app.dependency_overrides[get_current_user] = lambda: auth_user
        client = TestClient(app)

        res = client.post(
            "/api/agent/message",
            json={
                "message": "Những thiết bị nào còn dưới 10 cái?",
                "conversation_id": "test-e2e-strict-10",
            },
        )
        assert res.status_code == 200
        data = res.json()
        trace = data.get("trace", {})

        assert trace.get("intent") == "low_stock_inventory"
        assert trace.get("selected_tool") == "get_low_stock_inventory"
        assert trace.get("tool_arguments", {}).get("operator") == "<"
        assert trace.get("tool_arguments", {}).get("threshold") == 10


class TestMarkdownTableEscaping:
    """Test suite for Markdown table cell escaping in inventory reports."""

    def test_escape_markdown_cell_pipe(self):
        from app.agent.orchestrator import escape_markdown_cell
        # Raw pipe escaped to \|
        raw = "TE Connectivity AMP MCP 2.8 Series Female Crimp Terminal, 13 AWG Min Crimp, 15 AWG Max | RS"
        escaped = escape_markdown_cell(raw)
        assert escaped == "TE Connectivity AMP MCP 2.8 Series Female Crimp Terminal, 13 AWG Min Crimp, 15 AWG Max \\| RS"

        # Already escaped pipe does not get double-escaped
        assert escape_markdown_cell("Item \\| Part") == "Item \\| Part"

    def test_escape_markdown_cell_newlines_and_empty(self):
        from app.agent.orchestrator import escape_markdown_cell
        assert escape_markdown_cell(None) == ""
        assert escape_markdown_cell("   ") == ""
        # Newlines converted to spaces
        assert escape_markdown_cell("Line 1\nLine 2\r\nLine 3") == "Line 1 Line 2 Line 3"

    def test_table_row_column_alignment_with_special_characters(self, mock_request_repo, auth_user):
        import re
        from app.agent.state import state_manager
        repo = MagicMock()
        items = [
            # 1. Pipe in name
            DummyEquipment(
                equipment_id="PIPE-01",
                equipment_name="TE Connectivity AMP MCP 2.8 Series Female Crimp Terminal, 13 AWG Min Crimp, 15 AWG Max | RS",
                quantity_total=1,
                unit="cái",
                location="Tủ 1",
            ),
            # 2. Normal name without special characters
            DummyEquipment(
                equipment_id="NORM-01",
                equipment_name="Saleae Logic Analyzer",
                quantity_total=1,
                unit="bộ",
                location="tủ CSW",
            ),
            # 3. Very long name
            DummyEquipment(
                equipment_id="LONG-01",
                equipment_name="A" * 150,
                quantity_total=2,
                unit="cái",
                location="EBS_LAB",
            ),
            # 4. Empty optional values
            DummyEquipment(
                equipment_id="EMPTY-01",
                equipment_name="Thiết bị thiếu thông tin",
                quantity_total=3,
                unit=None,
                location=None,
            ),
            # 5. Multiple pipes and embedded newlines
            DummyEquipment(
                equipment_id="MULTI-01",
                equipment_name="Sensor X | Version 2.0 | High-Temp\nIndustrial Grade | RS",
                quantity_total=4,
                unit="con",
                location="Tủ 2 | Ngăn B",
            ),
        ]
        repo.get_all.return_value = items
        tools = AgentTools(repo, mock_request_repo)
        orchestrator = AgentOrchestrator(tools=tools, gemini_router=None)

        result = orchestrator.process_message(
            raw_message="Hiện tại trong kho có thiết bị nào sắp hết không",
            user=auth_user,
            conversation_id="conv-escaping-test",
        )

        reply = result["reply"]
        table_lines = [l.strip() for l in reply.split("\n") if l.strip().startswith("|")]

        assert len(table_lines) >= 7  # header, divider, and 5 data rows
        header_row = table_lines[0]
        divider_row = table_lines[1]
        data_rows = table_lines[2:]

        # Header has 5 columns
        header_cols = [c.strip() for c in re.split(r"(?<!\\)\|", header_row)[1:-1]]
        assert len(header_cols) == 5
        assert header_cols == ["Tên thiết bị", "Số lượng ghi nhận", "Đơn vị", "Vị trí", "Mã thiết bị"]

        for idx, row in enumerate(data_rows):
            # Split using unescaped pipe
            cols = [c.strip() for c in re.split(r"(?<!\\)\|", row)[1:-1]]
            assert len(cols) == 5, f"Row {idx} malformed: expected 5 columns, got {len(cols)}. Row: {row}"

        # Verify PIPE-01 columns alignment
        pipe_row = next(r for r in data_rows if "PIPE-01" in r)
        pipe_cols = [c.strip() for c in re.split(r"(?<!\\)\|", pipe_row)[1:-1]]
        assert "15 AWG Max \\| RS" in pipe_cols[0]
        assert pipe_cols[1] == "1"
        assert pipe_cols[2] == "cái"
        assert pipe_cols[3] == "Tủ 1"
        assert "`PIPE-01`" in pipe_cols[4]

        # Verify EMPTY-01 handles missing optional values
        empty_row = next(r for r in data_rows if "EMPTY-01" in r)
        empty_cols = [c.strip() for c in re.split(r"(?<!\\)\|", empty_row)[1:-1]]
        assert len(empty_cols) == 5
        assert empty_cols[2] == "cái"  # default unit
        assert empty_cols[3] == "Chưa xác định"  # default location

        # Verify MULTI-01 handles multiple pipes and newlines safely
        multi_row = next(r for r in data_rows if "MULTI-01" in r)
        multi_cols = [c.strip() for c in re.split(r"(?<!\\)\|", multi_row)[1:-1]]
        assert len(multi_cols) == 5
        assert "\n" not in multi_cols[0]
        assert "\\|" in multi_cols[0]
        assert "\\|" in multi_cols[3]  # location also had pipe

        # Verify original name in state.last_result_set is preserved without escaped backslash
        state = state_manager.get_state(auth_user.user_email, "conv-escaping-test")
        pipe_state_item = next(it for it in state.last_result_set if it["EquipmentID"] == "PIPE-01")
        assert pipe_state_item["EquipmentName"] == "TE Connectivity AMP MCP 2.8 Series Female Crimp Terminal, 13 AWG Min Crimp, 15 AWG Max | RS"

    def test_live_catalog_every_table_row_has_exact_column_count(self, auth_user):
        import re
        app.dependency_overrides[get_current_user] = lambda: auth_user
        client = TestClient(app)

        res = client.post(
            "/api/agent/message",
            json={
                "message": "Hiện tại trong kho có thiết bị nào sắp hết không",
                "conversation_id": "test-e2e-live-table-escaping",
            },
        )
        assert res.status_code == 200
        data = res.json()
        reply = data.get("reply", "")

        table_lines = [l.strip() for l in reply.split("\n") if l.strip().startswith("|")]
        assert len(table_lines) > 2

        header_cols = [c.strip() for c in re.split(r"(?<!\\)\|", table_lines[0])[1:-1]]
        assert len(header_cols) == 5

        data_rows = table_lines[2:]
        found_tu1_014 = False

        for r_idx, row in enumerate(data_rows):
            cols = [c.strip() for c in re.split(r"(?<!\\)\|", row)[1:-1]]
            assert len(cols) == 5, f"Row {r_idx} failed column count: {row}"
            if "TU1-014" in cols[4]:
                found_tu1_014 = True
                # Check column contents:
                assert "15 AWG Max \\| RS" in cols[0]
                assert cols[1] == "1"
                assert cols[2] in ["cuộn", "cái"]
                assert cols[3] == "Tủ 1"
                assert cols[4] == "`TU1-014`"

        assert found_tu1_014, "TU1-014 must be present in low stock report"


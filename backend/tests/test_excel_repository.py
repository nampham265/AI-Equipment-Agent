"""Tests for ExcelEquipmentRepository and ExcelRequestRepository."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
import pytest
import openpyxl

from app.core.config import settings
from app.repositories.excel_equipment import ExcelEquipmentRepository
from app.repositories.excel_request import ExcelRequestRepository
from app.models.excel_request import ExcelRequestModel


@pytest.fixture
def sample_workbook_path(tmp_path):
    """Copy the real workbook to a temporary location for safe testing."""
    real_path = settings.resolved_excel_path
    assert real_path.exists(), f"Source workbook must exist at {real_path}"
    
    test_file = tmp_path / "equipment_agent_repo_test.xlsx"
    if real_path.resolve() != test_file.resolve():
        shutil.copyfile(real_path, test_file)
    return test_file


class TestExcelEquipmentRepository:
    def test_load_real_workbook(self, sample_workbook_path):
        repo = ExcelEquipmentRepository(str(sample_workbook_path))
        items = repo.list_all()
        assert len(items) > 0
        assert repo.count() == len(items)

    def test_get_by_id(self, sample_workbook_path):
        repo = ExcelEquipmentRepository(str(sample_workbook_path))
        items = repo.list_all()
        first_item = items[0]
        
        found = repo.get_by_id(first_item.equipment_id)
        assert found is not None
        assert found.equipment_name == first_item.equipment_name
        assert found.quantity_total == first_item.quantity_total

    def test_get_by_id_nonexistent(self, sample_workbook_path):
        repo = ExcelEquipmentRepository(str(sample_workbook_path))
        assert repo.get_by_id("NONEXISTENT_XYZ_123") is None

    def test_search(self, sample_workbook_path):
        repo = ExcelEquipmentRepository(str(sample_workbook_path))
        items = repo.list_all()
        sample_name = items[0].equipment_name[:5]
        
        results = repo.search(sample_name)
        assert len(results) >= 1
        assert any(r.equipment_id == items[0].equipment_id for r in results)

    def test_missing_sheet_raises_error(self, tmp_path):
        bad_wb_path = tmp_path / "bad.xlsx"
        wb = openpyxl.Workbook()
        wb.active.title = "SomeOtherSheet"
        wb.save(bad_wb_path)
        wb.close()

        with pytest.raises(ValueError, match="thiếu sheet 'Equipment'"):
            ExcelEquipmentRepository(str(bad_wb_path))

    def test_missing_column_raises_error(self, tmp_path):
        bad_wb_path = tmp_path / "bad_cols.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Equipment"
        ws.append(["EquipmentID", "EquipmentName"])  # missing Category, etc.
        wb.save(bad_wb_path)
        wb.close()

        with pytest.raises(ValueError, match="thiếu các cột"):
            ExcelEquipmentRepository(str(bad_wb_path))


class TestExcelRequestRepository:
    def test_create_and_read_request(self, sample_workbook_path):
        repo = ExcelRequestRepository(str(sample_workbook_path))
        
        req = ExcelRequestModel(
            request_id="",
            requester_email="tester@company.com",
            requester_name="Tester",
            project="Project Apollo",
            equipment_id="TU1-001",
            equipment_name="Conn header SMD 24pos 3mm female",
            quantity=2,
            needed_from="2026-06-01",
            needed_to="2026-06-10",
            purpose="Testing connector",
            priority_level="High",
            priority_reason="Urgent project deliverable",
        )
        
        created = repo.create(req)
        assert created.request_id.startswith("REQ-")
        assert created.id > 0
        assert created.status == "Pending"
        assert created.final_priority_level is None
        assert created.created_at != ""
        assert created.updated_at != ""

        # Retrieve by id
        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.request_id == created.request_id
        assert fetched.requester_email == "tester@company.com"
        assert fetched.project == "Project Apollo"
        assert fetched.quantity == 2

    def test_list_by_requester(self, sample_workbook_path):
        repo = ExcelRequestRepository(str(sample_workbook_path))
        
        req = ExcelRequestModel(
            request_id="",
            requester_email="user1@company.com",
            requester_name="User One",
            project="Project A",
            equipment_id="TU1-001",
            equipment_name="Test Equipment",
            quantity=1,
            needed_from="2026-07-01",
            needed_to="2026-07-05",
            purpose="Test",
        )
        repo.create(req)

        results = repo.list_by_requester("user1@company.com")
        assert len(results) >= 1
        assert results[0].requester_email == "user1@company.com"

        empty_results = repo.list_by_requester("nobody@company.com")
        assert len(empty_results) == 0

    def test_update_status(self, sample_workbook_path):
        repo = ExcelRequestRepository(str(sample_workbook_path))
        
        req = ExcelRequestModel(
            request_id="",
            requester_email="user2@company.com",
            requester_name="User Two",
            project="Project B",
            equipment_id="TU1-002",
            equipment_name="Test Equipment 2",
            quantity=1,
            needed_from="2026-08-01",
            needed_to="2026-08-05",
            purpose="Test status update",
        )
        created = repo.create(req)
        first_updated_at = created.updated_at

        # Update status
        created.status = "Approved"
        updated = repo.update(created)
        assert updated.status == "Approved"
        assert updated.updated_at >= first_updated_at

        # Verify re-loaded from file
        reloaded = repo.get_by_id(created.id)
        assert reloaded.status == "Approved"

    def test_manager_priority_review_preserves_ai_fields(self, sample_workbook_path):
        repo = ExcelRequestRepository(str(sample_workbook_path))
        
        req = ExcelRequestModel(
            request_id="",
            requester_email="user3@company.com",
            requester_name="User Three",
            project="Project C",
            equipment_id="TU1-001",
            equipment_name="Test Equipment",
            quantity=1,
            needed_from="2026-09-01",
            needed_to="2026-09-05",
            purpose="Test priority review",
            priority_level="Low",
            priority_reason="AI evaluated as low priority",
        )
        created = repo.create(req)
        assert created.final_priority_level is None

        # Manager reviews priority
        review_time = datetime.now(timezone.utc).isoformat()
        created.final_priority_level = "High"
        created.priority_reviewed_by = "manager@company.com"
        created.priority_reviewed_at = review_time
        
        updated = repo.update(created)

        # FinalPriorityLevel is saved, but AI PriorityLevel and PriorityReason are unchanged!
        assert updated.final_priority_level == "High"
        assert updated.priority_reviewed_by == "manager@company.com"
        assert updated.priority_reviewed_at == review_time
        assert updated.priority_level == "Low"
        assert updated.priority_reason == "AI evaluated as low priority"

        # Re-check directly from disk
        reloaded = repo.get_by_id(created.id)
        assert reloaded.final_priority_level == "High"
        assert reloaded.priority_level == "Low"
        assert reloaded.priority_reason == "AI evaluated as low priority"

    def test_get_overlapping(self, sample_workbook_path):
        repo = ExcelRequestRepository(str(sample_workbook_path))
        
        req1 = ExcelRequestModel(
            request_id="",
            requester_email="u1@test.com",
            requester_name="U1",
            project="P1",
            equipment_id="EQ-OVERLAP-1",
            equipment_name="Eq Overlap",
            quantity=1,
            needed_from="2026-10-01",
            needed_to="2026-10-10",
            purpose="P",
            status="Approved",
        )
        c1 = repo.create(req1)

        # Overlapping range
        overlaps = repo.get_overlapping(
            equipment_id="EQ-OVERLAP-1",
            needed_from="2026-10-05",
            needed_to="2026-10-15",
            statuses=["Approved", "Borrowed"],
        )
        assert len(overlaps) == 1
        assert overlaps[0].id == c1.id

        # Non-overlapping range
        no_overlaps = repo.get_overlapping(
            equipment_id="EQ-OVERLAP-1",
            needed_from="2026-10-11",
            needed_to="2026-10-20",
            statuses=["Approved", "Borrowed"],
        )
        assert len(no_overlaps) == 0

    def test_count_by_status(self, sample_workbook_path):
        repo = ExcelRequestRepository(str(sample_workbook_path))
        
        req = ExcelRequestModel(
            request_id="",
            requester_email="u@test.com",
            requester_name="U",
            project="P",
            equipment_id="EQ-COUNT-1",
            equipment_name="Eq Count",
            quantity=1,
            needed_from="2026-11-01",
            needed_to="2026-11-05",
            purpose="P",
            status="Pending",
        )
        repo.create(req)

        counts = repo.count_by_status()
        assert counts.get("Pending", 0) >= 1

"""Regression test suite for DEFECT-01 (Partial Return) and DEFECT-02 (Rejection Reason).

Verifies persistence in both Excel and SQLite repositories, ensuring:
1. Partial return updates original record's quantity in storage and creates returned record.
2. Availability increases by exact returned quantity without double-counting.
3. Manager rejection reason is saved to dedicated field without altering AI priority assessment.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
import pytest
import openpyxl

from app.models.excel_request import ExcelRequestModel
from app.models.request import RequestModel
from app.repositories.excel_equipment import ExcelEquipmentRepository
from app.repositories.excel_request import ExcelRequestRepository
from app.repositories.sqlite_equipment import SQLiteEquipmentRepository
from app.repositories.sqlite_request import SQLiteRequestRepository
from app.schemas.requests import ReturnCondition
from app.services.approval_service import ApprovalService
from app.services.availability_service import AvailabilityService
from app.services.notification_service import NotificationService


class DummyNotificationProvider:
    def send_approval_notification(self, request, approved: bool) -> None:
        pass


@pytest.fixture
def temp_excel_workspace(tmp_path: Path):
    """Creates a temporary, fully valid Excel workbook with required sheets and headers."""
    wb_path = tmp_path / "test_equipment_agent.xlsx"
    wb = openpyxl.Workbook()

    # Sheet 1: Equipment
    ws_eq = wb.active
    ws_eq.title = "Equipment"
    ws_eq.append(["EquipmentID", "EquipmentName", "Category", "Description", "Quantity", "Unit", "Location"])
    ws_eq.append(["EQ-REG-001", "Digital Oscilloscope 100MHz", "Measurement", "Lab Scope", 10, "unit", "Lab A"])

    # Sheet 2: Equipment_Requests
    ws_req = wb.create_sheet("Equipment_Requests")
    ws_req.append([
        "RequestID", "RequesterEmail", "RequesterName", "Project",
        "EquipmentID", "EquipmentName", "Quantity", "NeededFrom", "NeededTo",
        "Purpose", "PriorityLevel", "PriorityReason", "FinalPriorityLevel",
        "PriorityReviewedBy", "PriorityReviewedAt", "Status",
        "ReturnCondition", "ReturnConditionNote", "ReturnedAt",
        "CreatedAt", "UpdatedAt", "RejectionReason"
    ])

    # Sheet 3: Users
    ws_u = wb.create_sheet("Users")
    ws_u.append(["UserEmail", "UserName", "Role", "IsActive"])
    ws_u.append(["manager@example.com", "Kho Manager", "MANAGER", "TRUE"])
    ws_u.append(["engineer@example.com", "Dev Engineer", "USER", "TRUE"])

    wb.save(wb_path)
    wb.close()
    return str(wb_path)


# ==============================================================================
# DEFECT-01: EXCEL PARTIAL RETURN & AVAILABILITY CALCULATION
# ==============================================================================

def test_defect_01_excel_partial_return_and_availability(temp_excel_workspace):
    """Regression test for DEFECT-01:
    1. Borrow 5 units out of 10.
    2. Available stock becomes 5.
    3. Return 2 units.
    4. Reload workbook from disk:
       - Original loan must have quantity = 3, status = 'Borrowed'
       - New cloned record must have quantity = 2, status = 'Returned'
    5. Available stock must increase by exactly 2 (to 7), with no double counting.
    """
    req_repo = ExcelRequestRepository(temp_excel_workspace)
    eq_repo = ExcelEquipmentRepository(temp_excel_workspace)
    notify_svc = NotificationService(DummyNotificationProvider())
    approval_svc = ApprovalService(req_repo, notify_svc)
    avail_svc = AvailabilityService(req_repo)

    # Check baseline availability: Total 10, Committed 0, Available 10
    avail_0 = avail_svc.calculate("EQ-REG-001", "2026-04-01", "2026-04-10", quantity_total=10)
    assert avail_0.quantity_total == 10
    assert avail_0.committed_quantity == 0
    assert avail_0.available_quantity == 10

    # 1. Create borrow request for 5 units
    req_model = ExcelRequestModel(
        request_id="REQ-20260401-000001",
        requester_email="engineer@example.com",
        requester_name="Dev Engineer",
        project="Radar Project",
        equipment_id="EQ-REG-001",
        equipment_name="Digital Oscilloscope 100MHz",
        quantity=5,
        needed_from="2026-04-01",
        needed_to="2026-04-10",
        purpose="Circuit debugging",
        priority_level="High",
        priority_reason="AI evaluated high impact",
        status="Pending",
        created_at="2026-04-01T08:00:00Z",
        updated_at="2026-04-01T08:00:00Z",
    )
    created = req_repo.create(req_model)
    req_id = created.id

    # Manager approves and hands over (marks borrowed)
    approval_svc.approve(req_id, actor_email="manager@example.com")
    approval_svc.mark_borrowed(req_id, actor_email="manager@example.com")

    # Verify inventory when 5 are borrowed
    avail_borrowed = avail_svc.calculate("EQ-REG-001", "2026-04-01", "2026-04-10", quantity_total=10)
    assert avail_borrowed.committed_quantity == 5
    assert avail_borrowed.available_quantity == 5

    # 2. Return 2 out of 5 units
    returned_read = approval_svc.mark_returned(
        request_id=req_id,
        return_condition=ReturnCondition.AS_RECEIVED.value,
        return_condition_note="Trả bớt 2 cái không dùng đến",
        actor_email="engineer@example.com",
        quantity=2,
    )

    # 3. Completely reload repository from disk to ensure persistence in Excel
    reloaded_req_repo = ExcelRequestRepository(temp_excel_workspace)
    reloaded_loan = reloaded_req_repo.get_by_id(req_id)

    # Verify original record
    assert reloaded_loan is not None
    assert reloaded_loan.quantity == 3, f"Expected 3 remaining units in Excel, got {reloaded_loan.quantity}"
    assert reloaded_loan.status == "Borrowed"

    # Verify all records for this requester to find the new cloned return record
    all_rows = reloaded_req_repo.list_all()
    assert len(all_rows) == 2, f"Expected 2 rows in Excel, got {len(all_rows)}"

    returned_row = next(r for r in all_rows if r.status == "Returned")
    assert returned_row.quantity == 2, f"Expected returned record quantity 2, got {returned_row.quantity}"
    assert returned_row.return_condition == ReturnCondition.AS_RECEIVED.value
    assert returned_row.return_condition_note == "Trả bớt 2 cái không dùng đến"
    assert returned_row.returned_at is not None

    # 4. Check available stock after partial return
    reloaded_avail_svc = AvailabilityService(reloaded_req_repo)
    avail_after = reloaded_avail_svc.calculate("EQ-REG-001", "2026-04-01", "2026-04-10", quantity_total=10)
    assert avail_after.committed_quantity == 3, f"Expected committed 3, got {avail_after.committed_quantity}"
    assert avail_after.available_quantity == 7, f"Expected available 7, got {avail_after.available_quantity}"
    assert avail_after.available_quantity == avail_borrowed.available_quantity + 2


# ==============================================================================
# DEFECT-02: EXCEL REJECTION REASON PERSISTENCE & AI INTEGRITY
# ==============================================================================

def test_defect_02_excel_rejection_reason_and_ai_integrity(temp_excel_workspace):
    """Regression test for DEFECT-02:
    1. Create a pending request with AI priority assessment:
       - priority_level = 'High'
       - priority_reason = 'AI priority assessment evidence: critical lab testing.'
    2. Manager rejects request with reason: 'Kho hết cáp nối tạm thời'.
    3. Reload workbook from disk:
       - rejection_reason must be exactly 'Kho hết cáp nối tạm thời'
       - priority_level must remain 'High'
       - priority_reason must remain 'AI priority assessment evidence: critical lab testing.'
       - status must be 'Rejected'
    """
    req_repo = ExcelRequestRepository(temp_excel_workspace)
    notify_svc = NotificationService(DummyNotificationProvider())
    approval_svc = ApprovalService(req_repo, notify_svc)

    ai_original_reason = "AI priority assessment evidence: critical lab testing."
    req_model = ExcelRequestModel(
        request_id="REQ-20260401-000002",
        requester_email="engineer@example.com",
        requester_name="Dev Engineer",
        project="ADAS",
        equipment_id="EQ-REG-001",
        equipment_name="Digital Oscilloscope 100MHz",
        quantity=1,
        needed_from="2026-04-05",
        needed_to="2026-04-08",
        purpose="Test ADAS sensors",
        priority_level="High",
        priority_reason=ai_original_reason,
        status="Pending",
        created_at="2026-04-01T08:00:00Z",
        updated_at="2026-04-01T08:00:00Z",
    )
    created = req_repo.create(req_model)
    req_id = created.id

    # Manager rejects request with specific reason
    rejection_text = "Kho hết cáp nối tạm thời, vui lòng mượn tuần sau."
    res = approval_svc.reject(
        request_id=req_id,
        reason=rejection_text,
        actor_email="manager@example.com",
    )
    assert res.status == "Rejected"
    assert res.rejection_reason == rejection_text
    assert res.priority_reason == ai_original_reason

    # Reload from disk using new repository instance
    reloaded_repo = ExcelRequestRepository(temp_excel_workspace)
    reloaded_model = reloaded_repo.get_by_id(req_id)

    assert reloaded_model is not None
    assert reloaded_model.status == "Rejected"
    assert reloaded_model.rejection_reason == rejection_text, (
        f"Expected rejection_reason '{rejection_text}', got '{reloaded_model.rejection_reason}'"
    )
    # AI assessment MUST NOT be overwritten or concatenated
    assert reloaded_model.priority_level == "High"
    assert reloaded_model.priority_reason == ai_original_reason, (
        f"AI priority_reason was unexpectedly altered: {reloaded_model.priority_reason}"
    )


# ==============================================================================
# SQLITE BACKEND VERIFICATION FOR BOTH DEFECTS
# ==============================================================================

def test_sqlite_partial_return_and_rejection_reason(tmp_path: Path):
    """Verifies that SQLite implementation also adheres to the same rules."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base
    import app.models.equipment  # noqa: F401
    import app.models.request  # noqa: F401

    db_url = f"sqlite:///{tmp_path}/test_app.db"
    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    req_repo = SQLiteRequestRepository(session)
    notify_svc = NotificationService(DummyNotificationProvider())
    approval_svc = ApprovalService(req_repo, notify_svc)

    # 1. Test partial return
    loan = RequestModel(
        requester_name="Engineer A",
        requester_email="eng@example.com",
        project="Alpha",
        equipment_id="EQ-01",
        quantity=5,
        needed_from="2026-04-01",
        needed_to="2026-04-10",
        purpose="Testing",
        priority_level="Medium",
        priority_reason="AI evaluation",
        status="Borrowed",
        created_at="2026-04-01T00:00:00Z",
        modified_at="2026-04-01T00:00:00Z",
    )
    req_repo.create(loan)
    loan_id = loan.id

    approval_svc.mark_returned(
        request_id=loan_id,
        return_condition=ReturnCondition.AS_RECEIVED.value,
        return_condition_note="Returning 2 units",
        actor_email="eng@example.com",
        quantity=2,
    )

    # Verify SQLite persistence
    session.expire_all()
    updated_loan = req_repo.get_by_id(loan_id)
    assert updated_loan.quantity == 3
    assert updated_loan.status == "Borrowed"

    all_loans = req_repo.list_all()
    assert len(all_loans) == 2
    returned_part = next(l for l in all_loans if l.status == "Returned")
    assert returned_part.quantity == 2

    # 2. Test rejection reason
    pending_req = RequestModel(
        requester_name="Engineer B",
        requester_email="eng2@example.com",
        project="Beta",
        equipment_id="EQ-02",
        quantity=1,
        needed_from="2026-04-01",
        needed_to="2026-04-05",
        purpose="Testing Beta",
        priority_level="Low",
        priority_reason="Original AI reason",
        status="Pending",
        created_at="2026-04-01T00:00:00Z",
        modified_at="2026-04-01T00:00:00Z",
    )
    req_repo.create(pending_req)
    pending_id = pending_req.id

    approval_svc.reject(
        request_id=pending_id,
        reason="Không đủ điều kiện dự án",
        actor_email="mgr@example.com",
    )

    session.expire_all()
    rejected_req = req_repo.get_by_id(pending_id)
    assert rejected_req.status == "Rejected"
    assert rejected_req.rejection_reason == "Không đủ điều kiện dự án"
    assert rejected_req.priority_reason == "Original AI reason"
    assert rejected_req.priority_level == "Low"

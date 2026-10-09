"""Excel-backed RequestRepository.

All requests are persisted to the 'Equipment_Requests' worksheet.

Safety guarantees:
- A threading.Lock serialises all write operations within a single process.
- A FileLock (via filelock) prevents concurrent access from multiple processes.
- Writes use a save-to-temp-then-replace strategy so the workbook is never
  left in a half-written state.
- UpdatedAt is refreshed on every write.

Column mapping (worksheet column → ExcelRequestModel attribute):
  RequestID          → request_id
  RequesterEmail     → requester_email
  RequesterName      → requester_name
  Project            → project
  EquipmentID        → equipment_id
  EquipmentName      → equipment_name
  Quantity           → quantity
  NeededFrom         → needed_from
  NeededTo           → needed_to
  Purpose            → purpose
  PriorityLevel      → priority_level
  PriorityReason     → priority_reason
  FinalPriorityLevel → final_priority_level
  PriorityReviewedBy → priority_reviewed_by
  PriorityReviewedAt → priority_reviewed_at
  Status             → status
  CreatedAt          → created_at
  UpdatedAt          → updated_at

LIMITATION: This implementation is intended for a single backend instance and
a small number of concurrent users.  FileLock guards against multi-process
corruption but does not provide transaction isolation.
"""
from __future__ import annotations

import logging
import os
import random
import string
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import openpyxl
from filelock import FileLock, Timeout

from app.models.excel_request import ExcelRequestModel
from app.repositories.base import RequestRepository

logger = logging.getLogger(__name__)

_SHEET_NAME = "Equipment_Requests"
_REQUIRED_COLUMNS = [
    "RequestID",
    "RequesterEmail",
    "RequesterName",
    "Project",
    "EquipmentID",
    "EquipmentName",
    "Quantity",
    "NeededFrom",
    "NeededTo",
    "Purpose",
    "PriorityLevel",
    "PriorityReason",
    "FinalPriorityLevel",
    "PriorityReviewedBy",
    "PriorityReviewedAt",
    "Status",
    "ReturnCondition",
    "ReturnConditionNote",
    "ReturnedAt",
    "CreatedAt",
    "UpdatedAt",
]

# Process-level write lock (single-process safety)
_WRITE_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_request_id(sequence_number: int) -> str:
    """Format: REQ-YYYYMMDD-NNNNNN where NNNNNN is zero-padded sequence."""
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"REQ-{date_part}-{sequence_number:06d}"


def _dates_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    """Return True if two date ranges overlap (inclusive on both ends)."""
    return start_a <= end_b and start_b <= end_a


class ExcelRequestRepository(RequestRepository):
    """Reads and writes equipment requests to the Excel workbook."""

    def __init__(self, workbook_path: str) -> None:
        self._path = Path(workbook_path)
        self._lock_path = Path(str(workbook_path) + ".lock")
        self._validate_workbook()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_workbook(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(
                f"Workbook không tồn tại: {self._path}. "
                "Kiểm tra EXCEL_DATA_PATH trong .env"
            )
        try:
            wb = openpyxl.load_workbook(self._path, read_only=True, data_only=True)
        except Exception as exc:
            raise RuntimeError(f"Không thể mở workbook {self._path}: {exc}") from exc

        if _SHEET_NAME not in wb.sheetnames:
            raise ValueError(
                f"Workbook thiếu sheet '{_SHEET_NAME}'. "
                f"Các sheet hiện có: {wb.sheetnames}"
            )

        ws = wb[_SHEET_NAME]
        first_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        headers = {str(c).strip() for c in first_row if c is not None}
        missing = set(_REQUIRED_COLUMNS) - headers
        if missing:
            raise ValueError(
                f"Sheet '{_SHEET_NAME}' thiếu các cột: {missing}. "
                f"Các cột hiện có: {headers}"
            )
        wb.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_workbook(self) -> openpyxl.Workbook:
        """Load a writable copy of the workbook."""
        return openpyxl.load_workbook(self._path, data_only=True)

    def _col_index(self, ws) -> dict[str, int]:
        """Build column-name → 1-indexed column number map from header row."""
        return {
            str(ws.cell(1, c).value).strip(): c
            for c in range(1, ws.max_column + 1)
            if ws.cell(1, c).value is not None
        }

    def _row_to_model(self, ws, row_num: int, col_idx: dict[str, int]) -> Optional[ExcelRequestModel]:
        def cell(name: str) -> Optional[str]:
            idx = col_idx.get(name)
            if idx is None:
                return None
            val = ws.cell(row_num, idx).value
            if val is None:
                return None
            return str(val).strip()

        def cell_int(name: str) -> int:
            v = cell(name)
            try:
                return int(v) if v else 0
            except ValueError:
                return 0

        req_id = cell("RequestID")
        if not req_id:
            return None

        return ExcelRequestModel(
            request_id=req_id,
            requester_email=cell("RequesterEmail") or "",
            requester_name=cell("RequesterName") or "",
            project=cell("Project") or "",
            equipment_id=cell("EquipmentID") or "",
            equipment_name=cell("EquipmentName") or "",
            quantity=cell_int("Quantity"),
            needed_from=cell("NeededFrom") or "",
            needed_to=cell("NeededTo") or "",
            purpose=cell("Purpose") or "",
            priority_level=cell("PriorityLevel") or "Needs review",
            priority_reason=cell("PriorityReason") or "",
            final_priority_level=cell("FinalPriorityLevel"),
            priority_reviewed_by=cell("PriorityReviewedBy"),
            priority_reviewed_at=cell("PriorityReviewedAt"),
            status=cell("Status") or "Pending",
            return_condition=cell("ReturnCondition"),
            return_condition_note=cell("ReturnConditionNote"),
            returned_at=cell("ReturnedAt"),
            created_at=cell("CreatedAt") or "",
            updated_at=cell("UpdatedAt") or "",
        )

    def _write_model_to_row(
        self, ws, row_num: int, col_idx: dict[str, int], model: ExcelRequestModel
    ) -> None:
        """Write all fields of model into the given worksheet row."""
        mapping = {
            "RequestID": model.request_id,
            "RequesterEmail": model.requester_email,
            "RequesterName": model.requester_name,
            "Project": model.project,
            "EquipmentID": model.equipment_id,
            "EquipmentName": model.equipment_name,
            "Quantity": model.quantity,
            "NeededFrom": model.needed_from,
            "NeededTo": model.needed_to,
            "Purpose": model.purpose,
            "PriorityLevel": model.priority_level,
            "PriorityReason": model.priority_reason,
            "FinalPriorityLevel": model.final_priority_level,
            "PriorityReviewedBy": model.priority_reviewed_by,
            "PriorityReviewedAt": model.priority_reviewed_at,
            "Status": model.status,
            "ReturnCondition": model.return_condition,
            "ReturnConditionNote": model.return_condition_note,
            "ReturnedAt": model.returned_at,
            "CreatedAt": model.created_at,
            "UpdatedAt": model.updated_at,
        }
        for col_name, value in mapping.items():
            idx = col_idx.get(col_name)
            if idx is not None:
                ws.cell(row_num, idx).value = value

    def _safe_save(self, wb: openpyxl.Workbook) -> None:
        """Save workbook atomically: write to temp file then rename with Windows lock retry."""
        import time
        tmp_path = self._path.with_suffix(".tmp")
        try:
            wb.save(tmp_path)
        finally:
            try:
                wb.close()
            except Exception:
                pass

        last_err = None
        for attempt in range(5):
            try:
                os.replace(tmp_path, self._path)
                return
            except PermissionError as pe:
                last_err = pe
                time.sleep(0.05 * (attempt + 1))
        if last_err:
            raise last_err

    def _load_all_rows(self) -> list[ExcelRequestModel]:
        wb = self._load_workbook()
        ws = wb[_SHEET_NAME]
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, ())
        col_idx = {str(h).strip(): i for i, h in enumerate(header_row) if h is not None}
        rows: list[ExcelRequestModel] = []
        for row in rows_iter:
            if not row:
                continue

            def cell(name: str) -> Optional[str]:
                idx = col_idx.get(name)
                if idx is None or idx >= len(row):
                    return None
                val = row[idx]
                return str(val).strip() if val is not None else None

            def cell_int(name: str) -> int:
                v = cell(name)
                try:
                    return int(v) if v else 0
                except ValueError:
                    return 0

            req_id = cell("RequestID")
            if not req_id:
                continue

            rows.append(
                ExcelRequestModel(
                    request_id=req_id,
                    requester_email=cell("RequesterEmail") or "",
                    requester_name=cell("RequesterName") or "",
                    project=cell("Project") or "",
                    equipment_id=cell("EquipmentID") or "",
                    equipment_name=cell("EquipmentName") or "",
                    quantity=cell_int("Quantity"),
                    needed_from=cell("NeededFrom") or "",
                    needed_to=cell("NeededTo") or "",
                    purpose=cell("Purpose") or "",
                    priority_level=cell("PriorityLevel") or "Needs review",
                    priority_reason=cell("PriorityReason") or "",
                    final_priority_level=cell("FinalPriorityLevel"),
                    priority_reviewed_by=cell("PriorityReviewedBy"),
                    priority_reviewed_at=cell("PriorityReviewedAt"),
                    status=cell("Status") or "Pending",
                    return_condition=cell("ReturnCondition"),
                    return_condition_note=cell("ReturnConditionNote"),
                    returned_at=cell("ReturnedAt"),
                    created_at=cell("CreatedAt") or "",
                    updated_at=cell("UpdatedAt") or "",
                )
            )
        wb.close()
        return rows

    def _next_sequence_number(self, wb: openpyxl.Workbook) -> int:
        """Find the max existing sequence number and return next one."""
        ws = wb[_SHEET_NAME]
        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, ())
        col_idx = {str(h).strip(): i for i, h in enumerate(header_row) if h is not None}
        req_id_idx = col_idx.get("RequestID")
        if req_id_idx is None:
            return 1
        max_seq = 0
        for row in rows_iter:
            if not row or req_id_idx >= len(row):
                continue
            val = row[req_id_idx]
            if val:
                try:
                    seq = int(str(val).split("-")[-1])
                    max_seq = max(max_seq, seq)
                except (ValueError, IndexError):
                    pass
        return max_seq + 1

    # ------------------------------------------------------------------
    # RequestRepository interface
    # ------------------------------------------------------------------

    def create(self, request) -> ExcelRequestModel:
        """Append a new request row. Returns the created ExcelRequestModel."""
        with _WRITE_LOCK:
            with FileLock(str(self._lock_path), timeout=10):
                wb = self._load_workbook()
                ws = wb[_SHEET_NAME]
                col_idx = self._col_index(ws)

                seq = self._next_sequence_number(wb)
                now = _now_iso()

                # Build model from incoming request (which may be RequestModel or ExcelRequestModel)
                model = ExcelRequestModel(
                    request_id=_generate_request_id(seq),
                    requester_email=getattr(request, "requester_email", "") or "",
                    requester_name=getattr(request, "requester_name", "") or "",
                    project=getattr(request, "project", ""),
                    equipment_id=getattr(request, "equipment_id", ""),
                    equipment_name=getattr(request, "equipment_name", ""),
                    quantity=getattr(request, "quantity", 0),
                    needed_from=str(getattr(request, "needed_from", "")),
                    needed_to=str(getattr(request, "needed_to", "")),
                    purpose=getattr(request, "purpose", ""),
                    priority_level=getattr(request, "priority_level", "Needs review"),
                    priority_reason=getattr(request, "priority_reason", ""),
                    final_priority_level=None,
                    priority_reviewed_by=None,
                    priority_reviewed_at=None,
                    status=getattr(request, "status", "Pending"),
                    return_condition=getattr(request, "return_condition", None),
                    return_condition_note=getattr(request, "return_condition_note", None),
                    returned_at=getattr(request, "returned_at", None),
                    created_at=now,
                    updated_at=now,
                )

                # Append to first empty row after data
                new_row = ws.max_row + 1
                self._write_model_to_row(ws, new_row, col_idx, model)
                self._safe_save(wb)
                wb.close()

                logger.info("Created request %s row %d", model.request_id, new_row)
                return model

    def get_by_id(self, request_id: int) -> Optional[ExcelRequestModel]:
        """Find a request by its numeric sequence id."""
        for model in self._load_all_rows():
            if model.id == request_id:
                return model
        return None

    def list_by_requester(self, requester_email: str) -> list[ExcelRequestModel]:
        email_lower = requester_email.lower()
        return [
            m for m in self._load_all_rows()
            if m.requester_email.lower() == email_lower
        ]

    def list_all(self, status: str | None = None) -> list[ExcelRequestModel]:
        rows = self._load_all_rows()
        if status:
            rows = [r for r in rows if r.status == status]
        return rows

    def update(self, request) -> ExcelRequestModel:
        """Update an existing request row in-place."""
        with _WRITE_LOCK:
            with FileLock(str(self._lock_path), timeout=10):
                wb = self._load_workbook()
                ws = wb[_SHEET_NAME]
                col_idx = self._col_index(ws)

                req_id_col = col_idx.get("RequestID")
                if req_id_col is None:
                    raise RuntimeError("RequestID column not found")

                target_id = getattr(request, "request_id", None)
                if target_id is None:
                    # Fall back to generating from int id
                    int_id = getattr(request, "id", None)
                    # Find by int id
                    for row_num in range(2, ws.max_row + 1):
                        val = ws.cell(row_num, req_id_col).value
                        if val:
                            try:
                                seq = int(str(val).split("-")[-1])
                                if seq == int_id:
                                    target_id = str(val)
                                    break
                            except (ValueError, IndexError):
                                pass

                # Find the row with matching RequestID
                found_row = None
                for row_num in range(2, ws.max_row + 1):
                    val = ws.cell(row_num, req_id_col).value
                    if val and str(val).strip() == target_id:
                        found_row = row_num
                        break

                if found_row is None:
                    wb.close()
                    raise ValueError(f"Yêu cầu {target_id} không tìm thấy trong workbook")

                # Read existing to preserve immutable fields
                existing = self._row_to_model(ws, found_row, col_idx)
                if existing is None:
                    wb.close()
                    raise ValueError(f"Không thể đọc yêu cầu tại row {found_row}")

                now = _now_iso()

                updated = ExcelRequestModel(
                    request_id=existing.request_id,
                    requester_email=existing.requester_email,
                    requester_name=existing.requester_name,
                    project=existing.project,
                    equipment_id=existing.equipment_id,
                    equipment_name=existing.equipment_name,
                    quantity=existing.quantity,
                    needed_from=existing.needed_from,
                    needed_to=existing.needed_to,
                    purpose=existing.purpose,
                    # AI assessment never modified after creation
                    priority_level=existing.priority_level,
                    priority_reason=existing.priority_reason,
                    # Manager review fields — use values from incoming if provided
                    final_priority_level=getattr(request, "final_priority_level", existing.final_priority_level),
                    priority_reviewed_by=getattr(request, "priority_reviewed_by", existing.priority_reviewed_by),
                    priority_reviewed_at=getattr(request, "priority_reviewed_at", existing.priority_reviewed_at),
                    # Mutable workflow field
                    status=getattr(request, "status", existing.status),
                    return_condition=getattr(request, "return_condition", existing.return_condition),
                    return_condition_note=getattr(request, "return_condition_note", existing.return_condition_note),
                    returned_at=getattr(request, "returned_at", existing.returned_at),
                    created_at=existing.created_at,
                    updated_at=now,
                )

                self._write_model_to_row(ws, found_row, col_idx, updated)
                self._safe_save(wb)
                wb.close()

                logger.info("Updated request %s to status=%s", updated.request_id, updated.status)
                return updated

    def get_overlapping(
        self,
        equipment_id: str,
        needed_from: str,
        needed_to: str,
        statuses: list[str],
        exclude_id: int | None = None,
    ) -> list[ExcelRequestModel]:
        """Return requests for the same equipment that overlap the date range."""
        results = []
        for model in self._load_all_rows():
            if model.equipment_id != equipment_id:
                continue
            if model.status not in statuses:
                continue
            if exclude_id is not None and model.id == exclude_id:
                continue
            if _dates_overlap(needed_from, needed_to, model.needed_from, model.needed_to):
                results.append(model)
        return results

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for model in self._load_all_rows():
            counts[model.status] = counts.get(model.status, 0) + 1
        return counts

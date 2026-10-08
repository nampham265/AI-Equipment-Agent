"""Excel-backed EquipmentRepository.

Reads equipment records from the 'Equipment' worksheet of the configured
workbook.  This repository is read-only (no writes to the Equipment sheet).

Column mapping (worksheet column → EquipmentModel attribute):
  EquipmentID   → equipment_id
  EquipmentName → equipment_name
  Category      → category
  Description   → description
  Quantity      → quantity_total
  Unit          → unit
  Location      → location
"""
from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Optional

import openpyxl

from app.models.equipment import EquipmentModel
from app.repositories.base import EquipmentRepository

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = {
    "EquipmentID",
    "EquipmentName",
    "Category",
    "Description",
    "Quantity",
    "Unit",
    "Location",
}

_SHEET_NAME = "Equipment"


def _normalize(text: str) -> str:
    """Lowercase + remove diacritics for accent-insensitive search."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


class ExcelEquipmentRepository(EquipmentRepository):
    """Reads equipment from the Excel workbook.  Thread-safe for concurrent reads.

    The workbook is loaded once into memory on init and re-loaded on every
    call to ensure up-to-date data in a long-running process.  For V1 scale
    (hundreds of rows) this is acceptable.
    """

    def __init__(self, workbook_path: str) -> None:
        self._path = Path(workbook_path)
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
        missing = _REQUIRED_COLUMNS - headers
        if missing:
            raise ValueError(
                f"Sheet '{_SHEET_NAME}' thiếu các cột: {missing}. "
                f"Các cột hiện có: {headers}"
            )
        wb.close()

    # ------------------------------------------------------------------
    # Internal loader
    # ------------------------------------------------------------------

    def _load_all(self) -> list[EquipmentModel]:
        wb = openpyxl.load_workbook(self._path, read_only=True, data_only=True)
        ws = wb[_SHEET_NAME]

        rows_iter = ws.iter_rows(values_only=True)
        header_row = next(rows_iter, ())
        col_idx: dict[str, int] = {}
        for i, h in enumerate(header_row):
            if h is not None:
                col_idx[str(h).strip()] = i

        items: list[EquipmentModel] = []
        for row in rows_iter:
            if not row:
                continue

            def cell(col_name: str) -> Optional[str]:
                idx = col_idx.get(col_name)
                if idx is None or idx >= len(row):
                    return None
                val = row[idx]
                return str(val).strip() if val is not None else None

            eq_id = cell("EquipmentID")
            eq_name = cell("EquipmentName")
            if not eq_id or not eq_name:
                continue  # skip blank / incomplete rows

            try:
                qty_raw = cell("Quantity")
                qty = int(qty_raw) if qty_raw is not None else 0
            except ValueError:
                qty = 0

            items.append(
                EquipmentModel(
                    equipment_id=eq_id,
                    equipment_name=eq_name,
                    category=cell("Category"),
                    description=cell("Description"),
                    quantity_total=qty,
                    unit=cell("Unit"),
                    location=cell("Location"),
                )
            )

        wb.close()
        return items

    # ------------------------------------------------------------------
    # EquipmentRepository interface
    # ------------------------------------------------------------------

    def list_all(self) -> list[EquipmentModel]:
        return self._load_all()

    def get_all(self) -> list[EquipmentModel]:
        return self._load_all()

    def search(self, query: str) -> list[EquipmentModel]:
        q = _normalize(query)
        results = []
        for item in self._load_all():
            haystack = " ".join(
                filter(
                    None,
                    [
                        item.equipment_id,
                        item.equipment_name,
                        item.category,
                        item.description,
                        item.location,
                    ],
                )
            )
            if q in _normalize(haystack):
                results.append(item)
        return results

    def get_by_id(self, equipment_id: str) -> Optional[EquipmentModel]:
        for item in self._load_all():
            if item.equipment_id == equipment_id:
                return item
        return None

    def count(self) -> int:
        return len(self._load_all())

    def bulk_upsert(self, items: list[EquipmentModel]) -> None:
        """Not supported — Equipment sheet is managed externally."""
        raise NotImplementedError(
            "ExcelEquipmentRepository does not support bulk_upsert. "
            "Edit the workbook directly."
        )

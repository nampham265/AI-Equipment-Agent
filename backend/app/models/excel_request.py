"""Plain dataclass model for Excel-backed EquipmentRequest rows.

This is NOT a SQLAlchemy ORM model. It mirrors the Equipment_Requests
worksheet columns exactly and is used only by ExcelRequestRepository.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExcelRequestModel:
    """Represents one row in the Equipment_Requests worksheet."""

    # --- identity ---
    request_id: str  # e.g. REQ-20241001-ABCDEF
    requester_email: str
    requester_name: str

    # --- borrow fields ---
    project: str
    equipment_id: str
    equipment_name: str
    quantity: int
    needed_from: str   # ISO date string YYYY-MM-DD
    needed_to: str     # ISO date string YYYY-MM-DD
    purpose: str

    # --- AI priority assessment (set once, never modified) ---
    priority_level: str = "Needs review"
    priority_reason: str = ""

    # --- Manager priority review (blank until manager explicitly reviews) ---
    final_priority_level: Optional[str] = None
    priority_reviewed_by: Optional[str] = None
    priority_reviewed_at: Optional[str] = None  # ISO datetime string

    # --- workflow ---
    status: str = "Pending"
    return_condition: Optional[str] = None
    return_condition_note: Optional[str] = None
    returned_at: Optional[str] = None
    created_at: str = ""   # ISO datetime string
    updated_at: str = ""   # ISO datetime string

    # -----------------------------------------------------------------------
    # Computed helpers
    # -----------------------------------------------------------------------

    @property
    def id(self) -> int:
        """Synthetic int id derived from request_id for API compatibility.

        The API layer uses int ids in URLs. We encode the integer suffix stored
        inside the request_id.  Format: REQ-YYYYMMDD-NNNNNN where NNNNNN is a
        zero-padded integer.
        """
        try:
            return int(self.request_id.split("-")[-1])
        except (ValueError, IndexError):
            return 0

    @property
    def display_id(self) -> str:
        return self.request_id

    @property
    def modified_at(self) -> str:
        """Alias for updated_at — read path used by _to_read() helpers."""
        return self.updated_at

    @modified_at.setter
    def modified_at(self, value: str) -> None:
        """Approval service sets modified_at; route it to updated_at."""
        self.updated_at = value

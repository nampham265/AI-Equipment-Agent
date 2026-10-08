"""Pydantic schemas for Manager dashboard endpoints."""
from __future__ import annotations

from pydantic import BaseModel


class ManagerSummary(BaseModel):
    # Frontend-facing field names
    pending_count: int = 0
    approved_count: int = 0
    borrowed_count: int = 0
    conflicts_count: int = 0
    # Extra info
    total_equipment: int = 0
    total_requests: int = 0

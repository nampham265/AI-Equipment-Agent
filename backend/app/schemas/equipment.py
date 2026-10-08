"""Pydantic schemas for Equipment domain."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EquipmentBase(BaseModel):
    equipment_id: str = Field(..., description="Unique equipment identifier, e.g. DEMO-EQ-001")
    equipment_name: str
    category: str | None = None
    description: str | None = None
    quantity_total: int = Field(..., ge=0)
    unit: str | None = None
    location: str | None = None


class EquipmentRead(EquipmentBase):
    model_config = {"from_attributes": True}


class EquipmentAvailability(BaseModel):
    equipment_id: str
    needed_from: str
    needed_to: str
    quantity_total: int
    committed_quantity: int
    available_quantity: int
    competing_pending_requests: list[PendingConflict]


class PendingConflict(BaseModel):
    id: str  # display id e.g. REQ-000001
    requester_name: str
    quantity: int
    needed_from: str
    needed_to: str
    project: str

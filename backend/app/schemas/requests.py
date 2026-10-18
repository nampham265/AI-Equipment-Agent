"""Pydantic schemas for EquipmentRequest domain."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class PriorityLevel(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    NEEDS_REVIEW = "Needs review"


class RequestStatus(str, Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    BORROWED = "Borrowed"
    RETURNED = "Returned"
    CANCELLED = "Cancelled"


# ---------------------------------------------------------------------------
# Identity helper (not stored in DB)
# ---------------------------------------------------------------------------

class DemoUser(BaseModel):
    name: str
    email: str
    role: str  # "user" | "manager"


# ---------------------------------------------------------------------------
# Request create / update
# ---------------------------------------------------------------------------

class RequestCreate(BaseModel):
    # requester_name/email are injected server-side from auth context; not required from client
    requester_name: str = Field(default="", min_length=0)
    requester_email: str | None = None
    project: str = Field(..., min_length=1)
    equipment_id: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    needed_from: date
    needed_to: date
    purpose: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def needed_to_gte_needed_from(self) -> "RequestCreate":
        if self.needed_to < self.needed_from:
            raise ValueError("needed_to phải lớn hơn hoặc bằng needed_from")
        return self


class RequestRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    display_id: str = ""  # e.g. REQ-000001
    requester_name: str
    requester_email: str | None = None
    project: str
    equipment_id: str
    equipment_name: str | None = None
    quantity: int
    needed_from: str  # ISO date string
    needed_to: str    # ISO date string
    purpose: str
    priority_level: str
    priority_reason: str
    # Manager priority review (separate from AI assessment, blank until reviewed)
    final_priority_level: Optional[str] = None
    priority_reviewed_by: Optional[str] = None
    priority_reviewed_at: Optional[str] = None
    status: str
    return_condition: Optional[str] = None
    return_condition_note: Optional[str] = None
    returned_at: Optional[str] = None
    created_at: str
    modified_at: str
    rejection_reason: Optional[str] = None


class ReturnCondition(str, Enum):
    AS_RECEIVED = "Nguyên trạng như khi nhận"
    MINOR_WEAR = "Có hao mòn nhẹ, vẫn sử dụng bình thường"
    MINOR_DAMAGE = "Hư hỏng nhẹ"
    MAJOR_DAMAGE = "Hư hỏng nặng"
    REPAIRED = "Hư hỏng nhưng đã khắc phục"
    NEEDS_INSPECTION = "Cần kiểm tra thêm"


class ReturnSubmitRequest(BaseModel):
    """Payload when user submits a return form."""
    return_condition: str = Field(..., description="Tình trạng khi trả")
    return_condition_note: Optional[str] = Field(default="", description="Ghi chú tình trạng khi trả (tuỳ chọn)")
    quantity: Optional[int] = Field(default=None, gt=0, description="Số lượng hoàn trả (mặc định trả toàn bộ)")

    @model_validator(mode="after")
    def validate_condition(self) -> "ReturnSubmitRequest":
        allowed = {c.value for c in ReturnCondition}
        if self.return_condition not in allowed:
            raise ValueError(f"Tình trạng khi trả không hợp lệ. Cho phép: {list(allowed)}")
        return self


class StatusUpdateRequest(BaseModel):
    reason: str | None = None  # optional rejection reason


class PriorityReviewRequest(BaseModel):
    """Body for manager priority review endpoint."""
    final_priority_level: str = Field(
        ...,
        description="Manager's confirmed priority: High, Medium, Low, or Needs review",
    )

    @model_validator(mode="after")
    def validate_priority(self) -> "PriorityReviewRequest":
        allowed = {"Critical", "High", "Medium", "Low", "Needs review"}
        if self.final_priority_level not in allowed:
            raise ValueError(f"final_priority_level phải là một trong: {allowed}")
        return self


# ---------------------------------------------------------------------------
# Priority assessment (AI output schema)
# ---------------------------------------------------------------------------

class PriorityAssessment(BaseModel):
    priority_level: PriorityLevel
    priority_reason: str = Field(..., max_length=1000)
    evidence: list[str] = Field(default_factory=list)
    needs_manager_review: bool = False

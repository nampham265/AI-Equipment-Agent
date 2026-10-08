"""Request service - handles creation, listing, and status queries."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.repositories.base import EquipmentRepository, RequestRepository
from app.schemas.requests import (
    PriorityLevel,
    RequestCreate,
    RequestRead,
    RequestStatus,
)
from app.services.priority_service import PriorityService

FALLBACK_REASON = (
    "Đánh giá ưu tiên tự động không thành công. "
    "Quản lý vui lòng xem xét."
)


def _to_read(r) -> RequestRead:
    """Convert any request model (SQLAlchemy or Excel dataclass) to RequestRead."""
    return RequestRead(
        id=r.id,
        display_id=r.display_id,
        requester_name=r.requester_name,
        requester_email=getattr(r, "requester_email", None),
        project=r.project,
        equipment_id=r.equipment_id,
        equipment_name=getattr(r, "equipment_name", None),
        quantity=r.quantity,
        needed_from=str(r.needed_from),
        needed_to=str(r.needed_to),
        purpose=r.purpose,
        priority_level=r.priority_level,
        priority_reason=r.priority_reason,
        final_priority_level=getattr(r, "final_priority_level", None),
        priority_reviewed_by=getattr(r, "priority_reviewed_by", None),
        priority_reviewed_at=getattr(r, "priority_reviewed_at", None),
        status=r.status,
        return_condition=getattr(r, "return_condition", None),
        return_condition_note=getattr(r, "return_condition_note", None),
        returned_at=getattr(r, "returned_at", None),
        created_at=str(r.created_at),
        modified_at=str(r.modified_at),
    )


class RequestService:
    def __init__(
        self,
        request_repo: RequestRepository,
        equipment_repo: EquipmentRepository,
        priority_service: PriorityService,
    ) -> None:
        self._req_repo = request_repo
        self._eq_repo = equipment_repo
        self._priority = priority_service

    def create_request(self, data: RequestCreate) -> RequestRead:
        from app.core.config import settings
        now = datetime.now(timezone.utc).isoformat()

        equipment = self._eq_repo.get_by_id(data.equipment_id)
        equipment_name = equipment.equipment_name if equipment else data.equipment_id

        if settings.DATA_BACKEND == "excel":
            # Use the Excel-native dataclass
            from app.models.excel_request import ExcelRequestModel
            model = ExcelRequestModel(
                request_id="",  # will be assigned by repo
                requester_email=data.requester_email or "",
                requester_name=data.requester_name,
                project=data.project,
                equipment_id=data.equipment_id,
                equipment_name=equipment_name,
                quantity=data.quantity,
                needed_from=data.needed_from.isoformat(),
                needed_to=data.needed_to.isoformat(),
                purpose=data.purpose,
                priority_level=PriorityLevel.NEEDS_REVIEW.value,
                priority_reason=FALLBACK_REASON,
                status=RequestStatus.PENDING.value,
                created_at=now,
                updated_at=now,
            )
        else:
            from app.models.request import RequestModel
            model = RequestModel(
                requester_name=data.requester_name,
                requester_email=data.requester_email,
                project=data.project,
                equipment_id=data.equipment_id,
                quantity=data.quantity,
                needed_from=data.needed_from.isoformat(),
                needed_to=data.needed_to.isoformat(),
                purpose=data.purpose,
                priority_level=PriorityLevel.NEEDS_REVIEW.value,
                priority_reason=FALLBACK_REASON,
                status=RequestStatus.PENDING.value,
                created_at=now,
                modified_at=now,
            )

        saved = self._req_repo.create(model)

        # Run priority assessment after saving so we have an ID
        if equipment:
            assessment = self._priority.assess(saved, equipment)
            saved.priority_level = assessment.priority_level.value
            saved.priority_reason = assessment.priority_reason
            saved.modified_at = datetime.now(timezone.utc).isoformat()
            saved = self._req_repo.update(saved)

        return _to_read(saved)

    def get_my_requests(self, requester_email: str) -> list[RequestRead]:
        items = self._req_repo.list_by_requester(requester_email)
        return [_to_read(r) for r in items]

    def get_request(self, request_id: int) -> Optional[RequestRead]:
        r = self._req_repo.get_by_id(request_id)
        return _to_read(r) if r else None

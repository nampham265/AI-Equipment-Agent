"""Priority service - orchestrates AI assessment with fallback."""
from __future__ import annotations

import logging
from typing import Any

from app.ai.base import LLMProvider
from app.models.equipment import EquipmentModel
from app.models.request import RequestModel
from app.repositories.base import RequestRepository
from app.schemas.requests import PriorityAssessment, PriorityLevel, RequestStatus

logger = logging.getLogger(__name__)

COMMITTED_STATUSES = [RequestStatus.APPROVED.value, RequestStatus.BORROWED.value]
PENDING_STATUS = [RequestStatus.PENDING.value]

FALLBACK_REASON = (
    "Đánh giá ưu tiên tự động không thành công. "
    "Quản lý vui lòng xem xét."
)


class PriorityService:
    def __init__(
        self,
        ai_provider: LLMProvider,
        request_repo: RequestRepository,
    ) -> None:
        self._ai = ai_provider
        self._repo = request_repo

    def assess(
        self,
        request: RequestModel,
        equipment: EquipmentModel,
    ) -> PriorityAssessment:
        """Run AI priority assessment and return a validated PriorityAssessment."""
        try:
            request_data = self._request_to_dict(request)
            context = self._build_context(request, equipment)
            raw = self._ai.assess_priority(request_data, context)
            assessment = PriorityAssessment(**raw)
            return assessment
        except Exception as exc:
            logger.error("Priority assessment failed: %s", exc, exc_info=True)
            return PriorityAssessment(
                priority_level=PriorityLevel.NEEDS_REVIEW,
                priority_reason=FALLBACK_REASON,
                evidence=[],
                needs_manager_review=True,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _request_to_dict(self, r: RequestModel) -> dict[str, Any]:
        return {
            "id": r.display_id,
            "requester_name": r.requester_name,
            "project": r.project,
            "equipment_id": r.equipment_id,
            "quantity": r.quantity,
            "needed_from": r.needed_from,
            "needed_to": r.needed_to,
            "purpose": r.purpose,
        }

    def _build_context(
        self,
        request: RequestModel,
        equipment: EquipmentModel,
    ) -> dict[str, Any]:
        overlapping_committed = self._repo.get_overlapping(
            equipment_id=request.equipment_id,
            needed_from=request.needed_from,
            needed_to=request.needed_to,
            statuses=COMMITTED_STATUSES,
            exclude_id=request.id,
        )
        overlapping_pending = self._repo.get_overlapping(
            equipment_id=request.equipment_id,
            needed_from=request.needed_from,
            needed_to=request.needed_to,
            statuses=PENDING_STATUS,
            exclude_id=request.id,
        )
        committed_qty = sum(r.quantity for r in overlapping_committed)

        return {
            "equipment": {
                "equipment_id": equipment.equipment_id,
                "equipment_name": equipment.equipment_name,
                "quantity_total": equipment.quantity_total,
                "category": equipment.category,
                "location": equipment.location,
            },
            "available_quantity": max(0, equipment.quantity_total - committed_qty),
            "overlapping_approved_borrowed": [
                self._request_to_dict(r) for r in overlapping_committed
            ],
            "overlapping_pending": [
                self._request_to_dict(r) for r in overlapping_pending
            ],
        }

"""Availability service - calculates committed and available quantities."""
from __future__ import annotations

from app.repositories.base import RequestRepository
from app.schemas.equipment import EquipmentAvailability, PendingConflict
from app.schemas.requests import RequestStatus

# Statuses that consume (commit) equipment
COMMITTED_STATUSES = [RequestStatus.APPROVED.value, RequestStatus.BORROWED.value]
PENDING_STATUS = [RequestStatus.PENDING.value]


class AvailabilityService:
    def __init__(self, request_repo: RequestRepository) -> None:
        self._repo = request_repo

    def calculate(
        self,
        equipment_id: str,
        needed_from: str,
        needed_to: str,
        quantity_total: int,
        exclude_request_id: int | None = None,
    ) -> EquipmentAvailability:
        """Compute availability for a date range.

        Args:
            equipment_id: The equipment to check.
            needed_from: ISO date string (YYYY-MM-DD).
            needed_to: ISO date string (YYYY-MM-DD).
            quantity_total: Total available units.
            exclude_request_id: Exclude this request from conflict calculation
                (used when editing/re-evaluating an existing request).
        """
        committed = self._repo.get_overlapping(
            equipment_id=equipment_id,
            needed_from=needed_from,
            needed_to=needed_to,
            statuses=COMMITTED_STATUSES,
            exclude_id=exclude_request_id,
        )
        committed_quantity = sum(r.quantity for r in committed)
        available_quantity = max(0, quantity_total - committed_quantity)

        pending = self._repo.get_overlapping(
            equipment_id=equipment_id,
            needed_from=needed_from,
            needed_to=needed_to,
            statuses=PENDING_STATUS,
            exclude_id=exclude_request_id,
        )
        competing = [
            PendingConflict(
                id=r.display_id,
                requester_name=r.requester_name,
                quantity=r.quantity,
                needed_from=r.needed_from,
                needed_to=r.needed_to,
                project=r.project,
            )
            for r in pending
        ]

        return EquipmentAvailability(
            equipment_id=equipment_id,
            needed_from=needed_from,
            needed_to=needed_to,
            quantity_total=quantity_total,
            committed_quantity=committed_quantity,
            available_quantity=available_quantity,
            competing_pending_requests=competing,
        )

"""Approval service - enforces state machine transitions."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.models.request import RequestModel
from app.repositories.base import RequestRepository
from app.schemas.requests import RequestRead, RequestStatus
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid state transitions
# ---------------------------------------------------------------------------
# Pending → Approved | Rejected | Cancelled
# Approved → Borrowed | Cancelled
# Borrowed → Returned

VALID_TRANSITIONS: dict[str, set[str]] = {
    RequestStatus.PENDING.value: {
        RequestStatus.APPROVED.value,
        RequestStatus.REJECTED.value,
        RequestStatus.CANCELLED.value,
    },
    RequestStatus.APPROVED.value: {
        RequestStatus.BORROWED.value,
        RequestStatus.CANCELLED.value,
    },
    RequestStatus.BORROWED.value: {
        RequestStatus.RETURNED.value,
    },
    RequestStatus.REJECTED.value: set(),
    RequestStatus.RETURNED.value: set(),
    RequestStatus.CANCELLED.value: set(),
}


def _to_read(r) -> RequestRead:
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


class ApprovalService:
    def __init__(
        self,
        request_repo: RequestRepository,
        notification_service: NotificationService,
    ) -> None:
        self._repo = request_repo
        self._notify = notification_service

    def _get_or_404(self, request_id: int) -> RequestModel:
        r = self._repo.get_by_id(request_id)
        if r is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không tìm thấy yêu cầu REQ-{request_id:06d}.",
            )
        return r

    def _transition(self, request: RequestModel, new_status: str) -> RequestModel:
        allowed = VALID_TRANSITIONS.get(request.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Không thể chuyển trạng thái từ '{request.status}' "
                    f"sang '{new_status}'."
                ),
            )
        request.status = new_status
        request.modified_at = datetime.now(timezone.utc).isoformat()
        return self._repo.update(request)

    # ------------------------------------------------------------------
    # Manager actions
    # ------------------------------------------------------------------

    def approve(self, request_id: int, actor_email: str | None = None) -> RequestRead:
        r = self._get_or_404(request_id)
        if actor_email and r.requester_email and r.requester_email.strip().lower() == actor_email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Người yêu cầu không thể tự phê duyệt yêu cầu mượn của chính mình.",
            )
        r = self._transition(r, RequestStatus.APPROVED.value)
        self._notify.notify_decision(r, approved=True)
        return _to_read(r)

    def reject(self, request_id: int, reason: str | None = None, actor_email: str | None = None) -> RequestRead:
        r = self._get_or_404(request_id)
        if actor_email and r.requester_email and r.requester_email.strip().lower() == actor_email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Người yêu cầu không thể tự từ chối yêu cầu mượn của chính mình.",
            )
        if reason:
            r.priority_reason = (r.priority_reason + f"\n[Từ chối: {reason}]").strip()
        r = self._transition(r, RequestStatus.REJECTED.value)
        self._notify.notify_decision(r, approved=False)
        return _to_read(r)

    def mark_borrowed(self, request_id: int, actor_email: str | None = None) -> RequestRead:
        r = self._get_or_404(request_id)
        if actor_email and r.requester_email and r.requester_email.strip().lower() == actor_email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Người yêu cầu không thể tự xác nhận mượn cho yêu cầu của chính mình.",
            )
        r = self._transition(r, RequestStatus.BORROWED.value)
        return _to_read(r)

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    def cancel(self, request_id: int, requester_email: str) -> RequestRead:
        r = self._get_or_404(request_id)
        # Users can only cancel their own requests
        if r.requester_email and r.requester_email != requester_email:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền huỷ yêu cầu này.",
            )
        r = self._transition(r, RequestStatus.CANCELLED.value)
        return _to_read(r)

    def mark_returned(
        self,
        request_id: int,
        return_condition: str | None = None,
        return_condition_note: str | None = None,
        actor_email: str | None = None,
        quantity: int | None = None,
    ) -> RequestRead:
        r = self._get_or_404(request_id)
        if actor_email and r.requester_email and r.requester_email.strip().lower() != actor_email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn chỉ có thể hoàn trả các yêu cầu mượn của chính mình.",
            )
        if r.status != RequestStatus.BORROWED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Không thể hoàn trả yêu cầu đang ở trạng thái '{r.status}'. Chỉ các yêu cầu đang mượn (Borrowed) mới có thể trả.",
            )
        if quantity is not None:
            if quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Số lượng hoàn trả phải lớn hơn 0.",
                )
            if quantity > r.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Số lượng hoàn trả ({quantity}) không thể lớn hơn số lượng đang mượn ({r.quantity}).",
                )

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Check for partial return
        if quantity is not None and 0 < quantity < r.quantity:
            # Create a clone of r for the returned portion
            if hasattr(r, "__table__"):
                returned_req = RequestModel(
                    requester_name=r.requester_name,
                    requester_email=r.requester_email,
                    project=r.project,
                    equipment_id=r.equipment_id,
                    quantity=quantity,
                    needed_from=r.needed_from,
                    needed_to=r.needed_to,
                    purpose=r.purpose,
                    priority_level=r.priority_level,
                    priority_reason=r.priority_reason,
                    status=RequestStatus.RETURNED.value,
                    return_condition=return_condition or "Nguyên trạng như khi nhận",
                    return_condition_note=return_condition_note or "",
                    returned_at=now_iso,
                    created_at=r.created_at,
                    modified_at=now_iso,
                )
                self._repo.create(returned_req)
            else:
                from app.models.excel_request import ExcelRequestModel
                returned_req = ExcelRequestModel(
                    request_id="",
                    requester_name=r.requester_name,
                    requester_email=r.requester_email,
                    project=r.project,
                    equipment_id=r.equipment_id,
                    equipment_name=r.equipment_name,
                    quantity=quantity,
                    needed_from=r.needed_from,
                    needed_to=r.needed_to,
                    purpose=r.purpose,
                    priority_level=r.priority_level,
                    priority_reason=r.priority_reason,
                    status=RequestStatus.RETURNED.value,
                    return_condition=return_condition or "Nguyên trạng như khi nhận",
                    return_condition_note=return_condition_note or "",
                    returned_at=now_iso,
                    created_at=r.created_at,
                    updated_at=now_iso,
                )
                self._repo.create(returned_req)

            # Update existing borrowed record with remaining quantity
            r.quantity -= quantity
            if hasattr(r, "modified_at"):
                r.modified_at = now_iso
            if hasattr(r, "updated_at"):
                r.updated_at = now_iso
            updated_loan = self._repo.update(r)
            return _to_read(updated_loan)

        # Full return
        if return_condition:
            r.return_condition = return_condition
        if return_condition_note is not None:
            r.return_condition_note = return_condition_note
        r.returned_at = now_iso
        r = self._transition(r, RequestStatus.RETURNED.value)
        return _to_read(r)

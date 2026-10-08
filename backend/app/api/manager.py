"""Manager API routes (protected - manager role required)."""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_manager
from app.core.config import settings
from app.repositories.factory import get_equipment_repo, get_request_repo
from app.auth.session import SessionData
from app.schemas.manager import ManagerSummary
from app.schemas.requests import PriorityReviewRequest, RequestRead, StatusUpdateRequest
from app.services.approval_service import ApprovalService
from app.services.notification_service import NotificationService
from app.notifications.console_provider import ConsoleNotificationProvider
from app.notifications.email_provider import EmailNotificationProvider

router = APIRouter(prefix="/api/manager", tags=["manager"])


def _get_notification_provider():
    if settings.EMAIL_NOTIFICATIONS_ENABLED:
        return EmailNotificationProvider()
    return ConsoleNotificationProvider()


def _approval_svc(db: Session = None) -> ApprovalService:
    req_repo = get_request_repo(db)
    notification_svc = NotificationService(_get_notification_provider())
    return ApprovalService(req_repo, notification_svc)


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


def _dates_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    """Return True if two date ranges overlap (inclusive on both ends)."""
    return str(start_a)[:10] <= str(end_b)[:10] and str(start_b)[:10] <= str(end_a)[:10]


@router.get("/requests")
def list_all_requests(
    status: str | None = Query(default=None, description="Filter by status"),
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> list[dict]:
    """List all requests (manager only), optionally filtered by status."""
    require_manager(current_user)
    req_repo = get_request_repo(db)
    eq_repo = get_equipment_repo(db)

    # Pre-fetch all equipment once into in-memory dictionary
    all_eq = eq_repo.list_all()
    eq_map = {eq.equipment_id: eq for eq in all_eq}

    # Pre-fetch all requests once
    all_requests = req_repo.list_all()

    from app.services.availability_service import COMMITTED_STATUSES, PENDING_STATUS

    # Filter by requested status if provided
    filtered_items = [r for r in all_requests if r.status == status] if status else all_requests

    result = []
    for r in filtered_items:
        eq = eq_map.get(r.equipment_id)
        eq_name = eq.equipment_name if eq else (getattr(r, "equipment_name", None) or r.equipment_id)

        # In-memory overlapping calculation
        committed = [
            c for c in all_requests
            if c.equipment_id == r.equipment_id
            and c.status in COMMITTED_STATUSES
            and c.id != r.id
            and _dates_overlap(r.needed_from, r.needed_to, c.needed_from, c.needed_to)
        ]
        pending = [
            p for p in all_requests
            if p.equipment_id == r.equipment_id
            and p.status in PENDING_STATUS
            and p.id != r.id
            and _dates_overlap(r.needed_from, r.needed_to, p.needed_from, p.needed_to)
        ]

        base = _to_read(r).model_dump()
        base["equipment_name"] = eq_name
        base["competing_approved_borrowed"] = [
            {
                "id": c.id,
                "requester_name": c.requester_name,
                "quantity": c.quantity,
                "needed_from": c.needed_from,
                "needed_to": c.needed_to,
                "project": c.project,
            }
            for c in committed
        ]
        base["competing_pending"] = [
            {
                "id": c.id,
                "requester_name": c.requester_name,
                "quantity": c.quantity,
                "needed_from": c.needed_from,
                "needed_to": c.needed_to,
                "project": c.project,
            }
            for c in pending
        ]
        result.append(base)
    return result


@router.get("/summary", response_model=ManagerSummary)
def get_summary(
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> ManagerSummary:
    """Return summary counts for the manager dashboard."""
    require_manager(current_user)
    req_repo = get_request_repo(db)
    eq_repo = get_equipment_repo(db)

    all_eq = eq_repo.list_all()
    all_requests = req_repo.list_all()
    eq_map = {eq.equipment_id: eq.equipment_name for eq in all_eq}

    counts: dict[str, int] = {}
    for r in all_requests:
        counts[r.status] = counts.get(r.status, 0) + 1

    pending = counts.get("Pending", 0)
    approved = counts.get("Approved", 0)
    borrowed = counts.get("Borrowed", 0)

    from app.services.conflict_service import ConflictService

    conflict_svc = ConflictService()
    conflict_pairs = conflict_svc.find_conflict_pairs(all_requests, eq_map)
    conflicts_count = len(conflict_pairs)

    return ManagerSummary(
        pending_count=pending,
        approved_count=approved,
        borrowed_count=borrowed,
        conflicts_count=conflicts_count,
        total_equipment=len(all_eq),
        total_requests=len(all_requests),
    )


@router.get("/conflicts")
def get_detailed_conflicts(
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> list[dict]:
    """List detailed schedule conflict pairs."""
    require_manager(current_user)
    req_repo = get_request_repo(db)
    eq_repo = get_equipment_repo(db)

    all_eq = eq_repo.list_all()
    eq_map = {eq.equipment_id: eq.equipment_name for eq in all_eq}
    all_requests = req_repo.list_all()

    from app.services.conflict_service import ConflictService

    conflict_svc = ConflictService()
    return conflict_svc.find_conflict_pairs(all_requests, eq_map)



@router.post("/requests/{request_id}/approve", response_model=RequestRead)
def approve_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> RequestRead:
    """Approve a pending request."""
    require_manager(current_user)
    return _approval_svc(db).approve(request_id, actor_email=current_user.user_email)


@router.post("/requests/{request_id}/reject", response_model=RequestRead)
def reject_request(
    request_id: int,
    body: StatusUpdateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> RequestRead:
    """Reject a pending request with an optional reason."""
    require_manager(current_user)
    reason = body.reason if body else None
    return _approval_svc(db).reject(request_id, reason=reason, actor_email=current_user.user_email)


@router.post("/requests/{request_id}/mark-borrowed", response_model=RequestRead)
def mark_borrowed(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> RequestRead:
    """Mark an approved request as borrowed (equipment handed over)."""
    require_manager(current_user)
    return _approval_svc(db).mark_borrowed(request_id, actor_email=current_user.user_email)


@router.patch("/requests/{request_id}/priority", response_model=RequestRead)
def review_request_priority(
    request_id: int,
    body: PriorityReviewRequest,
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> RequestRead:
    """Set manager's final priority level on a request.

    Preserves AI priority_level and priority_reason untouched.
    Records authenticated manager identity and server timestamp.
    """
    require_manager(current_user)
    req_repo = get_request_repo(db)
    req = req_repo.get_by_id(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy yêu cầu ID {request_id}")

    if req.requester_email and current_user.user_email and req.requester_email.strip().lower() == current_user.user_email.strip().lower():
        raise HTTPException(
            status_code=403,
            detail="Người yêu cầu không thể tự đánh giá độ ưu tiên cuối cùng cho yêu cầu của chính mình.",
        )

    req.final_priority_level = body.final_priority_level
    req.priority_reviewed_by = current_user.user_email or current_user.user_name
    req.priority_reviewed_at = datetime.now(timezone.utc).isoformat()

    updated = req_repo.update(req)
    return _to_read(updated)


_ATTENTION_CONDITIONS = {"Hư hỏng nhẹ", "Hư hỏng nặng", "Cần kiểm tra thêm"}


@router.get("/returns-review")
def get_returns_needing_review(
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> list[dict]:
    """Returns that need manager attention (damaged or uncertain condition)."""
    require_manager(current_user)
    req_repo = get_request_repo(db)

    returned = req_repo.list_all(status="Returned")
    results = []
    for r in returned:
        condition = getattr(r, "return_condition", None) or ""
        if condition in _ATTENTION_CONDITIONS:
            results.append({
                "id": r.id,
                "display_id": getattr(r, "display_id", f"REQ-{r.id:06d}"),
                "requester_name": r.requester_name,
                "requester_email": getattr(r, "requester_email", ""),
                "equipment_id": r.equipment_id,
                "equipment_name": getattr(r, "equipment_name", r.equipment_id),
                "project": r.project,
                "quantity": r.quantity,
                "needed_from": str(r.needed_from),
                "needed_to": str(r.needed_to),
                "status": r.status,
                "return_condition": condition,
                "return_condition_note": getattr(r, "return_condition_note", "") or "",
                "returned_at": getattr(r, "returned_at", "") or "",
            })
    return results

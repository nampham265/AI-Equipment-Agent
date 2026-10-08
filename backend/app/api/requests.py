"""Requests API routes (user-facing)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.config import settings
from app.repositories.factory import get_equipment_repo, get_request_repo
from app.auth.session import SessionData
from app.schemas.requests import RequestCreate, RequestRead, StatusUpdateRequest, ReturnSubmitRequest
from app.services.approval_service import ApprovalService
from app.services.notification_service import NotificationService
from app.services.priority_service import PriorityService
from app.services.request_service import RequestService

# AI and notification providers are resolved at import time based on config
from app.ai.demo_provider import DemoAIProvider
from app.ai.gemini_provider import GeminiAIProvider
from app.notifications.console_provider import ConsoleNotificationProvider
from app.notifications.email_provider import EmailNotificationProvider

router = APIRouter(prefix="/api/requests", tags=["requests"])


def _get_ai_provider():
    if settings.gemini_configured:
        return GeminiAIProvider(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
        )
    return DemoAIProvider()


def _get_notification_provider():
    if settings.EMAIL_NOTIFICATIONS_ENABLED:
        return EmailNotificationProvider()
    return ConsoleNotificationProvider()


def _build_services(db: Session = None):
    eq_repo = get_equipment_repo(db)
    req_repo = get_request_repo(db)
    priority_svc = PriorityService(_get_ai_provider(), req_repo)
    notification_svc = NotificationService(_get_notification_provider())
    request_svc = RequestService(req_repo, eq_repo, priority_svc)
    approval_svc = ApprovalService(req_repo, notification_svc)
    return request_svc, approval_svc


@router.post("", response_model=RequestRead, status_code=status.HTTP_201_CREATED)
def create_request(
    body: RequestCreate,
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> RequestRead:
    """Create a new borrow request. Triggers AI priority assessment."""
    # Validate equipment exists
    eq_repo = get_equipment_repo(db)
    equipment = eq_repo.get_by_id(body.equipment_id)
    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy thiết bị '{body.equipment_id}'.",
        )

    request_svc, _ = _build_services(db)
    # Inject the authenticated user's identity into the request
    body_with_user = body.model_copy(update={
        "requester_name": current_user.user_name,
        "requester_email": current_user.user_email,
    })
    return request_svc.create_request(body_with_user)


@router.get("/mine", response_model=list[RequestRead])
def get_my_requests(
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> list[RequestRead]:
    """Get all requests made by the current user (matched by email)."""
    request_svc, _ = _build_services(db)
    return request_svc.get_my_requests(current_user.user_email)


@router.post("/{request_id}/cancel", response_model=RequestRead)
def cancel_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> RequestRead:
    """Cancel a pending or approved (not yet borrowed) request."""
    _, approval_svc = _build_services(db)
    return approval_svc.cancel(request_id, current_user.user_email)


@router.post("/{request_id}/return", response_model=RequestRead)
def submit_return(
    request_id: int,
    body: ReturnSubmitRequest,
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> RequestRead:
    """Submit return for a borrowed equipment with condition and optional note."""
    _, approval_svc = _build_services(db)
    return approval_svc.mark_returned(
        request_id=request_id,
        return_condition=body.return_condition,
        return_condition_note=body.return_condition_note,
        actor_email=current_user.user_email,
    )


@router.post("/{request_id}/mark-returned", response_model=RequestRead)
def mark_returned(
    request_id: int,
    body: ReturnSubmitRequest | None = None,
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> RequestRead:
    """Mark a borrowed request as returned."""
    _, approval_svc = _build_services(db)
    return approval_svc.mark_returned(
        request_id=request_id,
        return_condition=body.return_condition if body else "Nguyên trạng như khi nhận",
        return_condition_note=body.return_condition_note if body else "",
        actor_email=current_user.user_email if not current_user.is_manager else None,
    )

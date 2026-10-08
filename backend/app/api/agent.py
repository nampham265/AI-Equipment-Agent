"""Agent chat API route with Orchestration, State, Multi-constraint Retrieval, and Grounded Tools."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent.orchestrator import AgentOrchestrator
from app.agent.tools import AgentTools
from app.ai.demo_provider import DemoAIProvider
from app.ai.gemini_provider import GeminiAIProvider
from app.auth.session import SessionData
from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.notifications.console_provider import ConsoleNotificationProvider
from app.notifications.email_provider import EmailNotificationProvider
from app.repositories.factory import (
    get_equipment_repo,
    get_request_repo,
    get_user_repo,
)
from app.schemas.agent import (
    AgentAction,
    AgentMessageRequest,
    AgentMessageResponse,
    BorrowFormPrefill,
)
from app.services.approval_service import ApprovalService
from app.services.availability_service import AvailabilityService
from app.services.notification_service import NotificationService
from app.services.priority_service import PriorityService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


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


@router.post("/message", response_model=AgentMessageResponse)
def agent_message(
    body: AgentMessageRequest,
    db: Session = Depends(get_db),
    current_user: SessionData = Depends(get_current_user),
) -> AgentMessageResponse:
    """Handle chat turn via the 8-step Agent Orchestration Pipeline."""
    eq_repo = get_equipment_repo(db)
    req_repo = get_request_repo(db)
    
    user_repo = None
    try:
        user_repo = get_user_repo()
    except Exception:
        pass

    ai_provider = _get_ai_provider()
    notif_provider = _get_notification_provider()
    priority_svc = PriorityService(ai_provider, req_repo)
    availability_svc = AvailabilityService(req_repo)
    notif_svc = NotificationService(notif_provider)
    approval_svc = ApprovalService(req_repo, notif_svc)

    tools = AgentTools(
        equipment_repo=eq_repo,
        request_repo=req_repo,
        user_repo=user_repo,
        priority_service=priority_svc,
        availability_service=availability_svc,
        approval_service=approval_svc,
    )
    orchestrator = AgentOrchestrator(tools)

    conv_id = body.conversation_id or "default"

    # Seed state from conversation_history if state is empty and history is provided
    # (e.g. for backward compatibility with clients passing history without backend persistence)
    # The orchestrator state manager will maintain the state natively.
    result = orchestrator.process_message(
        raw_message=body.message,
        user=current_user,
        conversation_id=conv_id,
    )

    action_obj = None
    if "action" in result and result["action"]:
        act = result["action"]
        # prefill is passed as a raw dict to support both borrow and return form types
        prefill_dict: Optional[dict[str, Any]] = None
        if "prefill" in act and act["prefill"]:
            pf = act["prefill"]
            if isinstance(pf, dict):
                prefill_dict = pf
            else:
                # Legacy: model instance → dict
                try:
                    prefill_dict = pf.model_dump()
                except AttributeError:
                    prefill_dict = dict(pf)
        action_obj = AgentAction(type=act.get("type", "show_borrow_form"), prefill=prefill_dict)

    return AgentMessageResponse(
        reply=result["reply"],
        action=action_obj,
        trace=result.get("trace"),
    )

"""Pydantic schemas for Agent (chat) endpoint."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class ConversationMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AgentMessageRequest(BaseModel):
    message: str
    conversation_history: list[ConversationMessage] = []
    conversation_id: Optional[str] = None


class BorrowFormPrefill(BaseModel):
    equipment_id: str = ""
    equipment_name: str = ""
    project: str = ""
    quantity: Optional[int] = None
    needed_from: Optional[str] = None
    needed_to: Optional[str] = None
    purpose: Optional[str] = None


class ReturnFormPrefill(BaseModel):
    request_id: int
    display_id: str = ""
    equipment_id: str = ""
    equipment_name: str = ""
    project: str = ""
    quantity: int = 1
    needed_from: str = ""
    needed_to: str = ""


class AgentAction(BaseModel):
    type: str  # e.g. "show_borrow_form", "show_return_form"
    prefill: Optional[dict[str, Any]] = None


class AgentMessageResponse(BaseModel):
    reply: str
    action: Optional[AgentAction] = None
    structured_data: Optional[dict[str, Any]] = None
    trace: Optional[dict[str, Any]] = None

"""Pydantic models and schemas for Agent Orchestration, Context & State."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.schemas.equipment import EquipmentRead
from app.schemas.requests import RequestRead


class IntentType(str, Enum):
    # Equipment intents
    EQUIPMENT_SEARCH = "equipment_search"
    EQUIPMENT_EXISTS = "equipment_exists"
    EQUIPMENT_DETAIL = "equipment_detail"
    EQUIPMENT_COUNT = "equipment_count"
    QUANTITY_SUFFICIENCY = "quantity_sufficiency"
    AVAILABILITY_QUERY = "availability_query"
    USAGE_QUERY = "usage_query"
    PROJECT_USAGE_QUERY = "project_usage_query"
    SCHEDULE_PLANNING = "schedule_planning"
    SCHEDULE_PLANNING_QUERY = "schedule_planning_query"
    EQUIPMENT_CONDITION_QUERY = "equipment_condition_query"
    ALTERNATIVE_SEARCH = "alternative_search"
    EXTERNAL_SOURCING = "external_sourcing"
    
    # Request intents
    REQUEST_CREATE = "request_create"
    MY_REQUESTS = "my_requests"
    RETURN_REQUEST = "return_request"
    
    # Manager intents
    PENDING_REQUEST_COUNT = "pending_request_count"
    PENDING_REQUEST_LIST = "pending_request_list"
    RECENT_REQUEST = "recent_request"
    RECENT_REQUESTS = "recent_requests"
    REQUEST_DETAIL = "request_detail"
    PRIORITY_REVIEW = "priority_review"
    APPROVE_REQUEST = "approve_request"
    REJECT_REQUEST = "reject_request"
    REQUEST_STATUS_UPDATE = "request_status_update"
    OVERDUE_LOANS = "overdue_loans"
    OVERDUE_BORROWERS = "overdue_borrowers"
    ACTIVE_LOANS = "active_loans"
    ACTIVE_LOANS_COUNT = "active_loans_count"
    ACTIVE_BORROWERS = "active_borrowers"
    ACTIVE_BORROWERS_COUNT = "active_borrowers_count"
    SCHEDULE_CONFLICTS = "schedule_conflicts"
    CONFLICT_BORROWERS = "conflict_borrowers"
    
    # Admin / System intents
    USER_MANAGEMENT = "user_management"
    LIST_USERS = "list_users"
    ADD_USER = "add_user"
    CANCEL_ACTION = "cancel_action"
    CLARIFICATION_REQUIRED = "clarification_required"
    HELP = "help"
    UNKNOWN = "unknown"


class LLMEquipmentEntity(BaseModel):
    equipment_id: Optional[str] = None
    equipment_name: Optional[str] = None


class LLMRequestEntity(BaseModel):
    request_id: Optional[int] = None
    quantity: Optional[int] = None
    project: Optional[str] = None
    purpose: Optional[str] = None
    needed_from: Optional[str] = None
    needed_to: Optional[str] = None
    negate_borrow: bool = False


class LLMConstraints(BaseModel):
    category: Optional[str] = None
    geometry: Optional[str] = None
    size_mm: Optional[float] = None
    pins: Optional[int] = None
    location: Optional[str] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)


class LLMReference(BaseModel):
    type: Optional[str] = "none"  # "none" | "active_equipment" | "active_request" | "previous_result" | "group_people" | "group_requests"
    ordinal_index: Optional[int] = None
    is_pronoun: bool = False
    is_group: bool = False
    is_group_reference: bool = False


class GeminiRouterOutput(BaseModel):
    intent: str
    confidence: float = 1.0
    equipment: LLMEquipmentEntity = Field(default_factory=LLMEquipmentEntity)
    request: LLMRequestEntity = Field(default_factory=LLMRequestEntity)
    constraints: LLMConstraints = Field(default_factory=LLMConstraints)
    reference: LLMReference = Field(default_factory=LLMReference)
    external_search_requested: bool = False
    is_negation_or_cancellation: bool = False
    action_cancelled: bool = False
    clarification_needed: bool = False
    clarification_reason: Optional[str] = None
    reasoning: Optional[str] = None


class ExtractedConstraints(BaseModel):
    category: Optional[str] = None
    location: Optional[str] = None
    geometry: Optional[str] = None  # e.g. "R/A", "right-angle", "SMD"
    size_mm: Optional[float] = None  # e.g. 4.2, 3.0, 4.0
    pins: Optional[int] = None       # e.g. 6, 8, 10, 16, 18, 24, 36
    color: Optional[str] = None      # e.g. "đen", "trắng", "black", "white"
    gender: Optional[str] = None     # e.g. "female", "male", "đực", "cái"
    keywords: list[str] = Field(default_factory=list)


class QueryPlan(BaseModel):
    intent: IntentType
    intent_confidence: float = 1.0
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    ordinal_index: Optional[int] = None  # 1-based index (e.g. 2 for "cái thứ 2")
    is_pronoun_reference: bool = False   # "nó", "thiết bị này", "đơn này"
    is_group_reference: bool = False     # "những người đó", "mấy người này", "các đơn trên"
    is_next_page: bool = False           # "xem tiếp", "tiếp theo"
    is_expand_detail: bool = False       # "cho mình xem chi tiết hơn", "xem chi tiết"
    constraints: ExtractedConstraints = Field(default_factory=ExtractedConstraints)
    
    # Request form fields (if extracted from message)
    quantity: Optional[int] = None
    needed_from: Optional[str] = None
    needed_to: Optional[str] = None
    project: Optional[str] = None
    purpose: Optional[str] = None
    
    # Request query filter (e.g. "Approved", "Pending", "Borrowed")
    status_filter: Optional[str] = None
    
    # Manager specific
    new_priority: Optional[str] = None  # e.g. "High", "Low"
    reject_reason: Optional[str] = None
    target_request_id: Optional[int] = None
    
    negate_borrow: bool = False
    ask_auto_approve: bool = False
    needs_clarification: bool = False
    raw_message: str = ""


class PendingForm(BaseModel):
    type: str = "borrow_request"
    equipment_id: str = ""
    equipment_name: str = ""
    quantity: Optional[int] = None
    needed_from: Optional[str] = None
    needed_to: Optional[str] = None
    project: str = ""
    purpose: str = ""


class ConversationState(BaseModel):
    conversation_id: str
    user_email: str
    last_intent: Optional[IntentType] = None
    last_query: Optional[str] = None
    active_equipment: Optional[dict[str, Any]] = None  # serialized EquipmentRead
    active_equipment_ids: list[str] = Field(default_factory=list)
    active_request: Optional[dict[str, Any]] = None    # serialized RequestRead
    active_request_ids: list[int] = Field(default_factory=list)
    last_result_set: list[dict[str, Any]] = Field(default_factory=list) # equipment, requests, or loans
    last_result_type: str = "equipment"  # "equipment" | "request" | "user_requests" | "overdue_loans" | "active_loans" | "active_borrowers"
    last_result_count: int = 0
    result_schema: Optional[str] = None
    last_result_page: int = 1
    last_page_size: int = 15
    last_selected_item: Optional[dict[str, Any]] = None
    pending_form: Optional[PendingForm] = None
    pending_action: Optional[str] = None
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentTrace(BaseModel):
    conversation_id: str
    user_role: str
    intent: str
    intent_confidence: float
    entities: dict[str, Any]
    constraints: dict[str, Any]
    resolved_context: dict[str, Any]
    resolved_references: list[str] = Field(default_factory=list)
    conversation_state_used: bool = False
    query_plan: dict[str, Any] = Field(default_factory=dict)
    selected_tool: Optional[str] = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    tool_result_type: Optional[str] = None
    tool_result_count: int = 0
    selected_result_ids: list[str] = Field(default_factory=list)
    fallback_reason: Optional[str] = None
    routing_mode: str = "legacy_fallback"  # "llm_primary" | "llm_shadow" | "legacy_fallback"
    llm_router_called: bool = False
    llm_input_summary: Optional[str] = None
    llm_raw_json: Optional[str] = None
    llm_intent: Optional[str] = None
    fallback_used: bool = False
    response_type: str = "grounded"  # "grounded", "table", "form", "clarification", "unsupported"
    response_mode: str = "grounded"  # "grounded", "fallback", "clarification", "unsupported"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

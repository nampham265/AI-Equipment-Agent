"""End-to-end Agent Orchestrator: Context, Planning, Deterministic Tools & Response."""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.agent.gemini_router import GeminiAgentRouter
from app.agent.models import (
    AgentTrace,
    ConversationState,
    ExtractedConstraints,
    GeminiRouterOutput,
    IntentType,
    PendingForm,
    QueryPlan,
)
from app.agent.normalizer import (
    check_ask_auto_approve,
    extract_request_id,
    normalize_equipment_ids,
    normalize_units,
    normalize_whitespace,
)
from app.agent.numeric import NumericExplanation
from app.agent.router import query_router
from app.agent.state import state_manager
from app.agent.tools import AgentTools
from app.auth.session import SessionData
from app.core.config import settings

logger = logging.getLogger(__name__)


def _to_dict(item: Any) -> dict[str, Any]:
    """Safely convert ORM, Pydantic, or dict object to dictionary."""
    if not item:
        return {}
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "__dict__"):
        d = dict(item.__dict__)
        d.pop("_sa_instance_state", None)
        return d
    if isinstance(item, dict):
        return item
    return {}


def _extract_int_req_id(d: Optional[dict]) -> Optional[int]:
    """Safely extract integer request id from dict."""
    if not d:
        return None
    val = d.get("id")
    if isinstance(val, int) and val > 0:
        return val
    req_str = str(d.get("RequestID") or d.get("request_id") or val or "")
    extracted = extract_request_id(req_str)
    if extracted is not None:
        return extracted
    m = re.search(r"(\d+)", req_str)
    return int(m.group(1)) if m else None


def escape_markdown_cell(
    value: Any,
    wrap_code: bool = False,
    wrap_bold: bool = False,
) -> str:
    """Safely format and escape an individual Markdown table cell value.

    - Handles None, empty, or non-string values safely.
    - Replaces embedded newlines (\\r, \\n, \\t) with a single space so table rows stay on 1 line.
    - Escapes literal pipe characters (| -> \\|) at the cell level.
    - Handles backticks safely when wrapping code spans.
    - Wraps in bold or code if requested, without breaking cell boundaries.
    """
    if value is None:
        raw_str = ""
    else:
        raw_str = str(value).strip()

    # Normalize embedded newlines and whitespace
    clean_str = re.sub(r"[\r\n\t]+", " ", raw_str).strip()

    # Escape pipe characters: replace | with \| (guard against double escaping existing \|)
    escaped_pipe = re.sub(r"(?<!\\)\|", r"\|", clean_str)

    if wrap_code:
        # Avoid nested or mismatched backticks breaking the code span
        safe_code = escaped_pipe.replace("`", "'")
        return f"`{safe_code}`" if safe_code else ""

    if wrap_bold:
        return f"**{escaped_pipe}**" if escaped_pipe else ""

    return escaped_pipe


def _map_gemini_to_plan(
    gemini_out: GeminiRouterOutput,
    raw_message: str,
    state: ConversationState,
) -> QueryPlan:
    """Map Gemini structured router output to verified backend QueryPlan."""
    raw_intent_str = str(gemini_out.intent).strip().lower()
    try:
        mapped_intent = IntentType(raw_intent_str)
    except ValueError:
        mapped_intent = IntentType.UNKNOWN

    is_cancelled = bool(gemini_out.is_negation_or_cancellation or getattr(gemini_out, "action_cancelled", False))
    if is_cancelled and mapped_intent in [IntentType.CANCEL_ACTION, IntentType.UNKNOWN]:
        mapped_intent = IntentType.CANCEL_ACTION

    plan = QueryPlan(
        intent=mapped_intent,
        intent_confidence=gemini_out.confidence,
        raw_message=raw_message,
        entity_id=gemini_out.equipment.equipment_id,
        entity_name=gemini_out.equipment.equipment_name,
        quantity=gemini_out.request.quantity,
        needed_from=gemini_out.request.needed_from,
        needed_to=gemini_out.request.needed_to,
        project=gemini_out.request.project,
        purpose=gemini_out.request.purpose,
        target_request_id=gemini_out.request.request_id,
        ordinal_index=gemini_out.reference.ordinal_index,
        is_pronoun_reference=gemini_out.reference.is_pronoun,
        is_group_reference=bool(gemini_out.reference.is_group or gemini_out.reference.is_group_reference),
        negate_borrow=bool(gemini_out.request.negate_borrow or gemini_out.is_negation_or_cancellation),
        low_stock_threshold=getattr(gemini_out, "low_stock_threshold", None),
        low_stock_operator=getattr(gemini_out, "low_stock_operator", None),
    )
    plan.ask_auto_approve = check_ask_auto_approve(raw_message.lower())

    lower_msg = raw_message.lower()

    # Check out-of-stock inventory intent guard (strictly Quantity == 0)
    is_out_of_stock_msg = (
        "sắp hết" not in lower_msg
        and (
            any(p in lower_msg for p in [
                "hết trong kho", "đã hết hàng", "hết hàng", "còn 0 cái", "hết sạch", "hết rồi không",
                "thiết bị nào hết", "món nào hết", "đã hết", "hết rồi", "hết chưa", "tồn bằng 0", "số lượng bằng 0"
            ])
            or (
                any(w in lower_msg for w in ["kho", "trong kho", "thiết bị", "món"])
                and any(w in lower_msg for w in ["hết hàng", "hết rồi", "còn 0 cái", "hết sạch", "nào hết"])
            )
        )
    ) and not plan.entity_id and not any(w in lower_msg for w in ["mượn", "borrow", "trả", "return"])

    if is_out_of_stock_msg:
        plan.intent = IntentType.OUT_OF_STOCK_INVENTORY
        plan.entity_id = None
        plan.entity_name = None

    # Check low-stock inventory intent guard
    is_low_stock_msg = (
        any(p in lower_msg for p in [
            "sắp hết", "còn ít", "tồn thấp", "số lượng tồn thấp", "cần bổ sung", "sắp cạn", "tồn kho thấp",
        ])
        or (
            any(w in lower_msg for w in ["kho", "trong kho", "thiết bị", "món"])
            and any(w in lower_msg for w in ["sắp hết", "còn ít", "cần bổ sung", "sắp cạn"])
        )
        or bool(re.search(r"(?:dưới|còn dưới)\s+(\d+)\s*(?:cái|chiếc|món|bộ)?", lower_msg))
        or bool(re.search(r"(\d+)\s*(?:cái|chiếc|món|bộ)?\s*trở\s*xuống", lower_msg))
        or bool(re.search(r"không\s*quá\s*(\d+)", lower_msg))
    )
    if is_low_stock_msg and not plan.entity_id and not any(w in lower_msg for w in ["mượn", "borrow", "trả", "return"]):
        plan.intent = IntentType.LOW_STOCK_INVENTORY
        plan.entity_id = None
        plan.entity_name = None

    if plan.intent == IntentType.LOW_STOCK_INVENTORY:
        m_strict = re.search(r"(?:còn\s+)?dưới\s+(\d+)", lower_msg)
        m_inc = re.search(r"(\d+)\s*(?:cái|chiếc|món|bộ)?\s*trở\s*xuống", lower_msg)
        m_no_more = re.search(r"không\s*quá\s*(\d+)", lower_msg)

        if m_strict:
            plan.low_stock_threshold = int(m_strict.group(1))
            plan.low_stock_operator = "<"
        elif m_inc:
            plan.low_stock_threshold = int(m_inc.group(1))
            plan.low_stock_operator = "<="
        elif m_no_more:
            plan.low_stock_threshold = int(m_no_more.group(1))
            plan.low_stock_operator = "<="

        # Clean bogus keywords/entities
        plan.entity_id = None
        plan.entity_name = None

    # Check personal loan inquiries
    is_my_loan_or_req = (
        any(p in lower_msg for p in [
            "của tôi", "của mình", "tôi gửi", "mình gửi", "tôi tạo", "mình tạo",
            "hiện mình đang mượn", "mình đang mượn", "tôi đang mượn", "mình mượn mấy thiết bị",
            "tôi mượn mấy thiết bị", "đang mượn mấy thiết bị", "hiện tôi đang mượn", "mình đang mượn những thiết bị nào"
        ])
    )
    if is_my_loan_or_req:
        if plan.intent in [IntentType.PENDING_REQUEST_LIST, IntentType.PENDING_REQUEST_COUNT, IntentType.ACTIVE_LOANS, IntentType.UNKNOWN]:
            plan.intent = IntentType.MY_REQUESTS
        elif any(p in lower_msg for p in ["hiện mình đang mượn", "mình đang mượn", "tôi đang mượn", "mấy thiết bị"]):
            plan.intent = IntentType.MY_REQUESTS
            plan.status_filter = "Borrowed"

    # Person refinement follow-up: "Nếu chỉ riêng Nam Phạm thôi thì sao"
    m_person = re.search(r"(?:nếu\s+)?(?:chỉ\s+)?riêng\s+([A-Za-zÀ-ỹ\s]+?)(?:\s+thôi)?(?:\s+thì\s+sao)?\??$", lower_msg)
    if m_person and (
        state.last_result_type in ["user_requests", "active_loans", "active_borrowers"]
        or state.last_intent in [IntentType.MY_REQUESTS, IntentType.ACTIVE_LOANS, IntentType.ACTIVE_BORROWERS, IntentType.ACTIVE_BORROWERS_COUNT]
    ):
        target_person_name = m_person.group(1).strip()
        plan.intent = IntentType.MY_REQUESTS if state.last_result_type == "user_requests" else IntentType.ACTIVE_LOANS
        plan.entity_name = target_person_name
        plan.status_filter = "Borrowed"

    # Hypothetical sufficiency follow-up check: "Nếu mình cần mượn 30 cái thì sao?", "Nếu chỉ mượn 5 cái thì sao?"
    m_hypo_qty = re.search(r"(?:nếu\s+)?(?:mình\s+|tôi\s+|em\s+)?(?:chỉ\s+)?(?:cần\s+|muốn\s+|lấy\s+)?(?:mượn\s+)?(\d+)\s*(?:cái|chiếc|con|bộ)?(?:\s+thì\s+sao|\s+được\s+không|\s+có\s+đủ\s+không|\s+đủ\s+không|\s+còn\s+dư\s+không)?\??$", lower_msg)
    if m_hypo_qty and (state.active_equipment or state.active_equipment_ids) and any(w in lower_msg for w in ["thì sao", "được không", "đủ không", "nếu", "chỉ"]):
        try:
            qty_val = int(m_hypo_qty.group(1))
            if 0 < qty_val < 10000:
                plan.quantity = qty_val
                active_eq = state.active_equipment or (state.last_selected_item if state.last_result_type == "equipment" else None)
                if active_eq:
                    plan.entity_id = active_eq.get("EquipmentID") or active_eq.get("equipment_id")
                    plan.entity_name = active_eq.get("EquipmentName") or active_eq.get("equipment_name")
                elif state.active_equipment_ids:
                    plan.entity_id = state.active_equipment_ids[0]
                plan.intent = IntentType.AVAILABILITY_QUERY
        except (ValueError, IndexError):
            pass

    # Enrich status filter for my_requests if not set
    if plan.intent == IntentType.MY_REQUESTS and not plan.status_filter:
        if any(w in lower_msg for w in ["đã được duyệt", "đã duyệt", "được duyệt", "approved"]):
            plan.status_filter = "Approved"
        elif any(w in lower_msg for w in ["chờ duyệt", "còn chờ", "đang chờ", "chưa duyệt", "pending"]):
            plan.status_filter = "Pending"
        elif any(w in lower_msg for w in ["đang mượn", "đang giữ", "chưa trả", "borrowed", "mấy thiết bị"]):
            plan.status_filter = "Borrowed"
        elif any(w in lower_msg for w in ["bị từ chối", "từ chối", "rejected", "bác bỏ"]):
            plan.status_filter = "Rejected"

    if gemini_out.constraints:
        c = gemini_out.constraints
        plan.constraints = ExtractedConstraints(
            category=c.category,
            location=c.location,
            geometry=c.geometry,
            size_mm=c.size_mm,
            pins=c.pins,
            color=c.color,
            keywords=c.keywords or [],
        )

    # 1. Ordinal resolution
    if plan.ordinal_index is not None and state.last_result_set:
        resolved_item = state_manager.get_item_by_ordinal(state, plan.ordinal_index)
        if resolved_item:
            if (
                state.last_result_type == "borrowed_loans"
                or state.pending_action in ["return", "return_select"]
                or "trả" in raw_message.lower()
                or plan.intent == IntentType.RETURN_REQUEST
            ):
                plan.intent = IntentType.RETURN_REQUEST
                plan.target_request_id = _extract_int_req_id(resolved_item)
            elif state.pending_action == "borrow_select":
                plan.intent = IntentType.REQUEST_CREATE
                plan.entity_id = str(resolved_item.get("EquipmentID") or resolved_item.get("equipment_id") or "")
                plan.entity_name = str(resolved_item.get("EquipmentName") or resolved_item.get("equipment_name") or "")
            elif state.last_result_type in ["request", "user_requests", "overdue_loans", "active_loans"]:
                if (
                    plan.intent in [IntentType.EQUIPMENT_DETAIL, IntentType.UNKNOWN, IntentType.USAGE_QUERY, IntentType.PROJECT_USAGE_QUERY]
                    or any(w in lower_msg for w in ["project nào", "dự án nào", "của ai", "thiết bị gì", "đơn"])
                ):
                    plan.intent = IntentType.REQUEST_DETAIL
                if not plan.target_request_id:
                    plan.target_request_id = _extract_int_req_id(resolved_item)
            elif state.last_result_type == "equipment":
                if any(w in raw_message.lower() for w in ["bao nhiêu", "mấy cái", "số lượng", "còn không", "còn bao nhiêu"]):
                    plan.intent = IntentType.EQUIPMENT_COUNT
                if not plan.entity_id:
                    plan.entity_id = str(resolved_item.get("EquipmentID") or resolved_item.get("equipment_id") or "")
                    plan.entity_name = str(resolved_item.get("EquipmentName") or resolved_item.get("equipment_name") or "")

    # 2. Pronoun resolution
    if plan.is_pronoun_reference:
        if plan.intent in [IntentType.REQUEST_DETAIL, IntentType.PRIORITY_REVIEW, IntentType.APPROVE_REQUEST, IntentType.REJECT_REQUEST]:
            if not plan.target_request_id and (state.active_request or state.last_selected_item):
                plan.target_request_id = _extract_int_req_id(state.active_request or state.last_selected_item)
        elif plan.intent in [
            IntentType.EQUIPMENT_DETAIL,
            IntentType.EQUIPMENT_COUNT,
            IntentType.AVAILABILITY_QUERY,
            IntentType.ALTERNATIVE_SEARCH,
            IntentType.PROJECT_USAGE_QUERY,
            IntentType.USAGE_QUERY,
        ]:
            if not plan.entity_id and (state.active_equipment or state.last_selected_item):
                item = state.active_equipment or state.last_selected_item
                plan.entity_id = str(item.get("EquipmentID") or item.get("equipment_id") or "")
                plan.entity_name = str(item.get("EquipmentName") or item.get("equipment_name") or "")

    # 3. Group reference resolution
    if plan.is_group_reference:
        if state.last_result_type in ["schedule_conflicts", "conflict_pairs"] or state.last_intent in [IntentType.SCHEDULE_CONFLICTS, IntentType.CONFLICT_BORROWERS, "schedule_conflicts", "conflict_borrowers"]:
            plan.intent = IntentType.CONFLICT_BORROWERS
        elif state.last_result_type in ["overdue_loans", "overdue_borrowers"] or state.last_intent in [IntentType.OVERDUE_LOANS, IntentType.OVERDUE_BORROWERS, "overdue_loans", "overdue_borrowers"]:
            plan.intent = IntentType.OVERDUE_BORROWERS
        elif state.last_result_type in ["active_loans", "active_borrowers"] or state.last_intent in [IntentType.ACTIVE_LOANS, IntentType.ACTIVE_BORROWERS, "active_loans", "active_borrowers"]:
            plan.intent = IntentType.ACTIVE_BORROWERS
        elif state.last_result_type in ["request", "user_requests"] or state.last_intent in [IntentType.MY_REQUESTS, IntentType.RECENT_REQUESTS, "user_requests", "my_requests", "recent_requests"]:
            plan.intent = IntentType.RECENT_REQUESTS

    # 4. Fallback entity resolution from state context
    if plan.intent == IntentType.REQUEST_DETAIL and not plan.target_request_id:
        if state.active_request:
            plan.target_request_id = _extract_int_req_id(state.active_request)
        elif state.active_request_ids:
            plan.target_request_id = state.active_request_ids[0]

    if plan.intent in [IntentType.EQUIPMENT_DETAIL, IntentType.EQUIPMENT_COUNT, IntentType.AVAILABILITY_QUERY, IntentType.ALTERNATIVE_SEARCH, IntentType.PROJECT_USAGE_QUERY, IntentType.USAGE_QUERY] and not plan.entity_id:
        if state.active_equipment:
            plan.entity_id = str(state.active_equipment.get("EquipmentID") or state.active_equipment.get("equipment_id") or "")
            plan.entity_name = str(state.active_equipment.get("EquipmentName") or state.active_equipment.get("equipment_name") or "")
        elif state.active_equipment_ids:
            plan.entity_id = state.active_equipment_ids[0]

    return plan


class AgentOrchestrator:
    """Central orchestrator executing the 8-step Agent pipeline with LLM + Rule routing."""

    def __init__(
        self,
        tools: AgentTools,
        gemini_router: Optional[GeminiAgentRouter] = None,
    ) -> None:
        self.tools = tools
        self.gemini_router = gemini_router

    def process_message(
        self,
        raw_message: str,
        user: SessionData,
        conversation_id: str,
    ) -> dict[str, Any]:
        """Main entrypoint for agent conversations."""
        # 1. State lookup
        state = state_manager.get_state(user.user_email, conversation_id)

        # 2. Routing selection
        routing_mode = getattr(settings, "AGENT_ROUTING_MODE", "llm_primary").lower()
        plan: Optional[QueryPlan] = None
        llm_called = False
        llm_intent_name: Optional[str] = None
        fallback_used = False
        fallback_reason: Optional[str] = None

        if routing_mode in ["llm_primary", "llm"]:
            if self.gemini_router:
                llm_called = True
                try:
                    gemini_out = self.gemini_router.classify_message(raw_message, user_role=user.role, state=state)
                    if gemini_out:
                        llm_intent_name = gemini_out.intent.value if hasattr(gemini_out.intent, "value") else str(gemini_out.intent)
                        plan = _map_gemini_to_plan(gemini_out, raw_message, state)
                except Exception as ex:
                    logger.warning("Gemini router error: %s. Falling back to deterministic router.", ex)
                    fallback_reason = str(ex)

            if not plan:
                fallback_used = True
                plan = query_router.route_message(raw_message, state)
                if not fallback_reason:
                    fallback_reason = "gemini_router_none_or_unconfigured"

        elif routing_mode == "shadow":
            plan = query_router.route_message(raw_message, state)
            if self.gemini_router:
                llm_called = True
                try:
                    gemini_out = self.gemini_router.classify_message(raw_message, user_role=user.role, state=state)
                    if gemini_out:
                        llm_intent_name = gemini_out.intent.value if hasattr(gemini_out.intent, "value") else str(gemini_out.intent)
                except Exception as ex:
                    logger.debug("Shadow router failed: %s", ex)
        else:
            # legacy_only
            plan = query_router.route_message(raw_message, state)

        resolved_mode = "legacy_only"
        if routing_mode == "shadow":
            resolved_mode = "llm_shadow"
        elif routing_mode in ["llm_primary", "llm"]:
            resolved_mode = "legacy_fallback" if fallback_used else "llm_primary"

        # 3. Create Trace object
        trace = AgentTrace(
            conversation_id=conversation_id,
            user_role=user.role.upper(),
            intent=plan.intent.value,
            intent_confidence=plan.intent_confidence,
            routing_mode=resolved_mode,
            llm_router_called=llm_called,
            llm_intent=llm_intent_name,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            entities={
                "entity": plan.entity_name or plan.entity_id,
                "entity_id": plan.entity_id,
                "entity_name": plan.entity_name,
                "target_request_id": plan.target_request_id,
                "ordinal_index": plan.ordinal_index,
            },
            constraints=plan.constraints.model_dump(),
            resolved_context={
                "active_equipment": state.active_equipment.get("EquipmentID") if state.active_equipment else None,
                "active_request": state.active_request.get("id") if state.active_request else None,
            },
            query_plan={
                "intent": plan.intent.value,
                "status_filter": plan.status_filter,
                "entity_id": plan.entity_id,
                "entity_name": plan.entity_name,
                "target_request_id": plan.target_request_id,
                "ordinal_index": plan.ordinal_index,
                "low_stock_threshold": plan.low_stock_threshold,
                "low_stock_operator": plan.low_stock_operator,
            },
            response_mode="grounded",
        )

        response_text = ""
        action_payload: Optional[dict[str, Any]] = None

        try:
            # 4. Route Execution based on intent
            if plan.intent == IntentType.EQUIPMENT_EXISTS:
                response_text, action_payload = self._handle_equipment_exists(plan, state, trace)

            elif plan.intent == IntentType.EQUIPMENT_SEARCH:
                response_text, action_payload = self._handle_equipment_search(plan, state, trace)

            elif plan.intent == IntentType.OUT_OF_STOCK_INVENTORY:
                response_text = self._handle_out_of_stock_inventory(plan, state, trace)

            elif plan.intent == IntentType.LOW_STOCK_INVENTORY:
                response_text = self._handle_low_stock_inventory(plan, state, trace)

            elif plan.intent == IntentType.ALTERNATIVE_SEARCH:
                response_text = self._handle_alternative_search(plan, state, trace)

            elif plan.intent == IntentType.EXTERNAL_SOURCING:
                response_text = self._handle_external_sourcing(plan, state, trace)

            elif plan.intent == IntentType.EQUIPMENT_COUNT:
                response_text = self._handle_equipment_count(plan, state, trace)

            elif plan.intent == IntentType.QUANTITY_SUFFICIENCY:
                response_text = self._handle_quantity_sufficiency(plan, state, trace)

            elif plan.intent == IntentType.EQUIPMENT_DETAIL:
                response_text = self._handle_equipment_detail(plan, state, trace)

            elif plan.intent == IntentType.AVAILABILITY_QUERY:
                response_text = self._handle_availability_query(plan, state, trace)

            elif plan.intent == IntentType.PROJECT_USAGE_QUERY:
                response_text = self._handle_project_usage(plan, state, trace)

            elif plan.intent == IntentType.USAGE_QUERY:
                response_text = self._handle_usage_query(plan, state, trace)

            elif plan.intent in [IntentType.SCHEDULE_PLANNING, IntentType.SCHEDULE_PLANNING_QUERY]:
                response_text = self._handle_schedule_planning(plan, state, trace)

            elif plan.intent == IntentType.EQUIPMENT_CONDITION_QUERY:
                response_text = self._handle_condition_query(plan, state, trace)

            elif plan.intent == IntentType.REQUEST_CREATE:
                response_text, action_payload = self._handle_request_create(plan, state, user, trace)

            elif plan.intent == IntentType.MY_REQUESTS:
                response_text = self._handle_my_requests(plan, user, state, trace)

            elif plan.intent == IntentType.RETURN_REQUEST:
                response_text, action_payload = self._handle_return_request(plan, user, state, trace)

            elif plan.intent == IntentType.CANCEL_ACTION:
                response_text, action_payload = self._handle_cancel_action(state, trace)

            # Manager intents
            elif plan.intent == IntentType.PENDING_REQUEST_COUNT:
                response_text = self._handle_pending_request_count(user, trace)

            elif plan.intent == IntentType.PENDING_REQUEST_LIST:
                response_text = self._handle_pending_request_list(user, state, trace)

            elif plan.intent == IntentType.RECENT_REQUEST:
                response_text = self._handle_recent_request(user, state, trace)

            elif plan.intent == IntentType.RECENT_REQUESTS:
                response_text = self._handle_recent_requests(plan, user, state, trace)

            elif plan.intent == IntentType.OVERDUE_LOANS:
                response_text = self._handle_overdue_loans(state, trace)

            elif plan.intent == IntentType.OVERDUE_BORROWERS:
                response_text = self._handle_overdue_borrowers(state, trace)

            elif plan.intent == IntentType.ACTIVE_LOANS:
                response_text = self._handle_active_loans(plan, user, state, trace)

            elif plan.intent == IntentType.ACTIVE_LOANS_COUNT:
                response_text = self._handle_active_loans_count(state, trace)

            elif plan.intent == IntentType.ACTIVE_BORROWERS:
                response_text = self._handle_active_borrowers(state, trace)

            elif plan.intent == IntentType.ACTIVE_BORROWERS_COUNT:
                response_text = self._handle_active_borrowers_count(state, trace)

            elif plan.intent == IntentType.SCHEDULE_CONFLICTS:
                response_text = self._handle_schedule_conflicts(state, trace)

            elif plan.intent == IntentType.CONFLICT_BORROWERS:
                response_text = self._handle_conflict_borrowers(state, trace)

            elif plan.intent == IntentType.REQUEST_DETAIL:
                response_text = self._handle_request_detail(plan, state, user, trace)

            elif plan.intent == IntentType.PRIORITY_REVIEW:
                response_text = self._handle_priority_review(plan, state, user, trace)

            elif plan.intent == IntentType.APPROVE_REQUEST:
                response_text = self._handle_approve_request(plan, state, user, trace)

            elif plan.intent == IntentType.REJECT_REQUEST:
                response_text = self._handle_reject_request(plan, state, user, trace)

            # Admin intents
            elif plan.intent == IntentType.ADD_USER:
                response_text = self._handle_add_user(plan, user, trace)

            elif plan.intent in [IntentType.USER_MANAGEMENT, IntentType.LIST_USERS]:
                response_text = self._handle_user_management(user, trace)

            elif plan.intent == IntentType.CLARIFICATION_REQUIRED:
                response_text = "Bạn có thể cung cấp thêm chi tiết về thiết bị hoặc yêu cầu được không?"
                trace.response_mode = "clarification"

            elif plan.intent == IntentType.HELP:
                response_text = self._handle_help(user)

            else:
                response_text = (
                    "Tôi chưa hiểu rõ yêu cầu của bạn. Bạn có thể tra cứu thiết bị "
                    "(ví dụ: `connector góc vuông 4.2mm ở Tủ 1`), kiểm tra số lượng, hoặc yêu cầu mượn thiết bị."
                )
                trace.response_mode = "fallback"

        except Exception as ex:
            logger.exception("Error processing agent turn: %s", ex)
            response_text = f"Đã xảy ra lỗi trong quá trình xử lý yêu cầu: {str(ex)}"
            trace.fallback_reason = str(ex)
            trace.response_mode = "error"

        # 5. Persist updated state
        state.last_intent = plan.intent
        state.last_query = raw_message
        state_manager.save_state(state)

        trace.conversation_state_used = bool(state.last_result_set or state.active_equipment or state.active_request)
        if plan.is_pronoun_reference:
            trace.resolved_references.append("pronoun")
        if plan.ordinal_index is not None:
            trace.resolved_references.append(f"ordinal_{plan.ordinal_index}")
        if plan.is_group_reference:
            trace.resolved_references.append("group_reference")

        logger.info(
            "AGENT_OBSERVABILITY [conv=%s] role=%s intent=%s conf=%.2f tool=%s res_type=%s count=%d mode=%s",
            conversation_id,
            user.role,
            plan.intent.value,
            plan.intent_confidence,
            trace.selected_tool,
            trace.tool_result_type or state.last_result_type,
            trace.tool_result_count,
            trace.response_mode,
        )

        result: dict[str, Any] = {"reply": response_text}
        if action_payload:
            result["action"] = action_payload
        result["trace"] = trace.model_dump()
        return result

    # -------------------------------------------------------------
    # Intent Handlers
    # -------------------------------------------------------------

    def _handle_equipment_exists(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> tuple[str, Optional[dict[str, Any]]]:
        trace.selected_tool = "search_equipment"
        search_query = plan.entity_name or plan.entity_id or " ".join(plan.constraints.keywords)
        trace.tool_arguments = {
            "query": search_query,
            "exact_id": plan.entity_id,
        }

        results = self.tools.search_equipment(plan.constraints, query=search_query, exact_id=plan.entity_id)
        trace.tool_result_count = len(results)
        trace.selected_result_ids = [r.equipment_id for r in results[:15]]

        if not results:
            trace.response_mode = "not_found"
            entity_label = plan.entity_name or plan.entity_id or search_query
            return (
                f"Không tìm thấy thiết bị {entity_label} trong dữ liệu hiện tại.",
                None,
            )

        # Store in state
        serialized_results = [_to_dict(r) for r in results]
        state_manager.set_result_set(state, serialized_results, result_type="equipment", page=1, page_size=15)

        if len(results) == 1:
            eq = results[0]
            state.active_equipment = serialized_results[0]
            state.active_equipment_ids = [eq.equipment_id]
            reply = (
                f"Có, thiết bị **{eq.equipment_name}** (`{eq.equipment_id}`) hiện có trong kho tại vị trí **{eq.location or 'Chưa xác định'}** "
                f"với tổng số lượng là **{eq.quantity_total} {eq.unit or 'cái'}**."
            )
            return (reply, None)

        lines = [f"Có, tìm thấy {len(results)} thiết bị phù hợp trong kho:\n"]
        for it in results[:5]:
            lines.append(
                f"• **{it.equipment_name}** (`{it.equipment_id}`) — "
                f"Tổng số lượng: {it.quantity_total} {it.unit or 'cái'} | Vị trí: {it.location}"
            )
        return ("\n".join(lines), None)

    def _handle_equipment_search(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> tuple[str, Optional[dict[str, Any]]]:
        trace.selected_tool = "search_equipment"
        page_size = 15
        
        # Check if pagination next page
        if plan.is_next_page and state.last_result_set and state.last_result_type == "equipment":
            next_page = state.last_result_page + 1
            items, page, total_pages, remaining = state_manager.get_page_items(state, next_page)
            if not items:
                return ("Bạn đã xem hết danh sách kết quả tìm kiếm trong kho.", None)
            
            total_items = len(state.last_result_set)
            start_idx = (page - 1) * page_size + 1
            end_idx = min(start_idx + len(items) - 1, total_items)

            lines = [f"📋 Danh sách thiết bị tiếp theo (từ {start_idx} đến {end_idx} / tổng số {total_items}):\n"]
            for it in items:
                lines.append(
                    f"• **{it.get('equipment_name')}** (`{it.get('equipment_id')}`) — "
                    f"Tổng số lượng: {it.get('quantity_total')} {it.get('unit', 'cái')} | Vị trí: {it.get('location')}"
                )
            if remaining > 0:
                lines.append(f"\n*(Còn {remaining} thiết bị khác. Bạn có thể nhắn 'xem tiếp' để xem trang kế tiếp hoặc nhập tên để tra cứu nhanh)*")
            else:
                lines.append(f"\n*(Đã hiển thị toàn bộ {total_items} thiết bị trong kho)*")
            return ("\n".join(lines), None)

        # Fresh search: extract clean search query, NOT the full natural language sentence
        search_query = plan.entity_name or plan.entity_id or " ".join(plan.constraints.keywords)
        trace.tool_arguments = {
            "query": search_query,
            "exact_id": plan.entity_id,
        }
        results = self.tools.search_equipment(plan.constraints, query=search_query, exact_id=plan.entity_id)
        trace.tool_result_count = len(results)
        trace.selected_result_ids = [r.equipment_id for r in results[:15]]

        if not results:
            trace.response_mode = "not_found"
            clean_target = plan.entity_name or plan.entity_id or search_query or "yêu cầu"
            return (
                f"Không tìm thấy thiết bị {clean_target} trong dữ liệu hiện tại.",
                None,
            )

        # Store in state
        serialized_results = [_to_dict(r) for r in results]
        state_manager.set_result_set(state, serialized_results, result_type="equipment", page=1, page_size=page_size)

        # If exactly 1 match, set as active
        if len(results) == 1:
            state.active_equipment = serialized_results[0]
            state.active_equipment_ids = [results[0].equipment_id]

        items, page, total_pages, remaining = state_manager.get_page_items(state, 1)
        total_items = len(results)
        end_idx = min(len(items), total_items)
        lines = [f"📋 Danh sách thiết bị trong hệ thống (từ 1 đến {end_idx} / tổng số {total_items}):\n"]
        for it in items:
            lines.append(
                f"• **{it.get('equipment_name')}** (`{it.get('equipment_id')}`) — "
                f"Tổng số lượng: {it.get('quantity_total')} {it.get('unit', 'cái')} | Vị trí: {it.get('location')}"
            )
        if remaining > 0:
            lines.append(f"\n*(Còn {remaining} thiết bị khác. Bạn có thể nhắn 'xem tiếp' để xem trang kế tiếp hoặc nhập tên để tra cứu nhanh)*")

        return ("\n".join(lines), None)

    def _handle_out_of_stock_inventory(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_out_of_stock_inventory"
        trace.tool_arguments = {}

        result = self.tools.get_out_of_stock_inventory()
        items = result["items"]
        total = result["total_matches"]

        trace.tool_result_count = total
        trace.tool_result_type = "out_of_stock_inventory"
        trace.selected_result_ids = [it["equipment_id"] for it in items]

        # Update conversation state with matching items
        serialized_items = [
            {
                "EquipmentID": it["equipment_id"],
                "EquipmentName": it["equipment_name"],
                "Quantity": it["recorded_quantity"],
                "Unit": it["unit"],
                "Location": it["location"],
                "Category": it["category"],
            }
            for it in items
        ]
        state_manager.set_result_set(state, serialized_items, result_type="equipment", page=1, page_size=15)

        if total == 0:
            trace.response_mode = "grounded"
            return (
                "Hiện tại trong kho không có thiết bị nào đã hết hàng (số lượng ghi nhận = 0). "
                "Toàn bộ thiết bị đều đang có số lượng tồn kho > 0.\n\n"
                "*(Lưu ý: Báo cáo dựa trên số lượng tồn kho ghi nhận trong hệ thống)*"
            )

        # Build Markdown table
        lines = [
            "📊 **Báo cáo thiết bị đã hết hàng trong kho (số lượng ghi nhận: 0)**\n",
            f"Hệ thống ghi nhận **{total}** thiết bị có số lượng tồn kho bằng 0:\n",
            "| Tên thiết bị | Số lượng ghi nhận | Đơn vị | Vị trí | Mã thiết bị |",
            "| :--- | :---: | :---: | :--- | :--- |",
        ]

        for it in items:
            name_cell = escape_markdown_cell(it.get("equipment_name") or "Chưa đặt tên", wrap_bold=True)
            qty_cell = escape_markdown_cell(it.get("recorded_quantity") if it.get("recorded_quantity") is not None else 0)
            unit_cell = escape_markdown_cell(it.get("unit") or "cái")
            loc_cell = escape_markdown_cell(it.get("location") or "Chưa xác định")
            id_cell = escape_markdown_cell(it.get("equipment_id") or "N/A", wrap_code=True)
            lines.append(f"| {name_cell} | {qty_cell} | {unit_cell} | {loc_cell} | {id_cell} |")

        lines.append(
            "\n*(Lưu ý: Danh sách trên thể hiện các thiết bị có số lượng ghi nhận bằng 0 trong kho. Vui lòng liên hệ Quản lý nếu cần bổ sung).* "
        )

        trace.response_mode = "grounded"
        return "\n".join(lines)

    def _handle_low_stock_inventory(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_low_stock_inventory"
        configured_default = getattr(settings, "LOW_STOCK_THRESHOLD", 5)

        thresh = plan.low_stock_threshold
        op = plan.low_stock_operator or "<="

        if thresh is None or not isinstance(thresh, int) or thresh <= 0:
            thresh = configured_default

        trace.tool_arguments = {
            "threshold": thresh,
            "operator": op,
        }

        result = self.tools.get_low_stock_inventory(threshold=thresh, operator=op)
        items = result["items"]
        total = result["total_matches"]
        eff_thresh = result["threshold"]
        eff_op = result["operator"]

        trace.tool_result_count = total
        trace.tool_result_type = "low_stock_inventory"
        trace.selected_result_ids = [it["equipment_id"] for it in items]

        # Update conversation state with matching items
        serialized_items = [
            {
                "EquipmentID": it["equipment_id"],
                "EquipmentName": it["equipment_name"],
                "Quantity": it["recorded_quantity"],
                "Unit": it["unit"],
                "Location": it["location"],
                "Category": it["category"],
            }
            for it in items
        ]
        state_manager.set_result_set(state, serialized_items, result_type="equipment", page=1, page_size=15)

        op_desc = f"dưới {eff_thresh} cái" if eff_op == "<" else f"từ {eff_thresh} cái trở xuống"

        if total == 0:
            trace.response_mode = "grounded"
            return (
                f"Hiện tại trong kho không có thiết bị nào có số lượng tồn {op_desc}. "
                f"Toàn bộ thiết bị đều đang có số lượng ghi nhận trên ngưỡng này.\n\n"
                f"*(Lưu ý: Báo cáo dựa trên số lượng tồn kho ghi nhận trong hệ thống)*"
            )

        # Build Markdown table
        lines = [
            f"📊 **Báo cáo thiết bị có số lượng tồn thấp (ngưỡng: {op_desc})**\n",
            f"Hệ thống ghi nhận **{total}** thiết bị đạt điều kiện tồn kho:\n",
            "| Tên thiết bị | Số lượng ghi nhận | Đơn vị | Vị trí | Mã thiết bị |",
            "| :--- | :---: | :---: | :--- | :--- |",
        ]

        for it in items:
            name_cell = escape_markdown_cell(it.get("equipment_name") or "Chưa đặt tên", wrap_bold=True)
            qty_cell = escape_markdown_cell(it.get("recorded_quantity") if it.get("recorded_quantity") is not None else 0)
            unit_cell = escape_markdown_cell(it.get("unit") or "cái")
            loc_cell = escape_markdown_cell(it.get("location") or "Chưa xác định")
            id_cell = escape_markdown_cell(it.get("equipment_id") or "N/A", wrap_code=True)
            lines.append(f"| {name_cell} | {qty_cell} | {unit_cell} | {loc_cell} | {id_cell} |")

        lines.append(
            f"\n*(Lưu ý: Danh sách trên thể hiện số lượng ghi nhận trong cơ sở dữ liệu kho nhằm hỗ trợ nhận diện các thiết bị có thể cần bổ sung. Hệ thống không tự động đưa ra quyết định mua hàng hay tạo đơn mua sắm).* "
        )

        trace.response_mode = "grounded"
        return "\n".join(lines)

    def _handle_equipment_count(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_equipment_count"
        eq_id = plan.entity_id

        # If user provided search keywords/constraints, search first instead of falling back to stale context
        query_text = plan.entity_name or " ".join(plan.constraints.keywords) or plan.raw_message
        has_new_subject = bool(plan.entity_name or plan.constraints.keywords or plan.constraints.category or plan.constraints.location or plan.constraints.geometry or plan.constraints.color)
        if not eq_id and has_new_subject:
            matched = self.tools.search_equipment(plan.constraints, query=query_text)
            if len(matched) == 1:
                eq_id = matched[0].equipment_id
            elif len(matched) > 1:
                serialized_results = [_to_dict(r) for r in matched]
                state_manager.set_result_set(state, serialized_results, result_type="equipment", page=1, page_size=15)

                unique_types = set(r.equipment_id for r in matched)
                is_type_count = any(w in plan.raw_message.lower() for w in ["bao nhiêu loại", "mấy loại", "có bao nhiêu loại", "có mấy loại", "số loại"])

                if is_type_count:
                    total_units = sum(r.quantity_total for r in matched)
                    target_label = plan.entity_name or " ".join(plan.constraints.keywords) or "thiết bị"
                    lines = [
                        f"📊 Hiện tại trong kho có **{len(unique_types)} loại** {target_label} khác nhau (với tổng cộng **{total_units}** đơn vị/cái).\n",
                        "Dưới đây là một số loại tiêu biểu:\n",
                    ]
                    for r in matched[:8]:
                        lines.append(
                            f"• **{r.equipment_name}** (`{r.equipment_id}`): {r.quantity_total} {r.unit or 'cái'} (Vị trí: {r.location or 'N/A'})"
                        )
                    if len(matched) > 8:
                        lines.append(f"\n*(Còn {len(matched) - 8} loại khác. Bạn có thể nhắn 'xem tiếp' để xem danh sách)*")
                    return "\n".join(lines)

                lines = [f"📊 Tìm thấy **{len(matched)}** thiết bị phù hợp trong kho:\n"]
                for r in matched[:10]:
                    c = self.tools.get_equipment_count(r.equipment_id)
                    incon_tag = " ⚠️ *(Số liệu bất thường: Đang mượn > Tồn kho)*" if c.get("has_inconsistency") else ""
                    lines.append(
                        f"• **{r.equipment_name}** (`{r.equipment_id}`): "
                        f"Khả dụng **{c.get('available_quantity', 0)}** {c.get('unit', 'cái')} "
                        f"(Tổng: {c.get('quantity_total', 0)} | Đang mượn: {c.get('borrowed_quantity', 0)} | Vị trí: {c.get('location', 'N/A')}){incon_tag}"
                    )
                if len(matched) > 10:
                    lines.append(f"\n*(Còn {len(matched) - 10} thiết bị khác)*")
                return "\n".join(lines)
            elif len(matched) == 0:
                clean_target = plan.entity_name or query_text
                return f"Không tìm thấy thiết bị nào phù hợp với '{clean_target}' trong kho."

        # Fallback to active context if no new subject was provided
        if not eq_id:
            if state.active_equipment:
                eq_id = state.active_equipment.get("EquipmentID")
            elif state.active_equipment_ids:
                eq_id = state.active_equipment_ids[0]

        if not eq_id:
            return "Bạn muốn kiểm tra số lượng của thiết bị nào? Vui lòng cung cấp mã hoặc tên thiết bị."

        info = self.tools.get_equipment_count(eq_id)
        if not info.get("found"):
            return f"Không tìm thấy thiết bị có mã `{eq_id}` trong kho."

        # Update active equipment
        state.active_equipment = {
            "EquipmentID": info["equipment_id"],
            "EquipmentName": info["equipment_name"],
            "Quantity": info["quantity_total"],
            "Location": info["location"],
        }
        state.active_equipment_ids = [info["equipment_id"]]

        explanation = NumericExplanation.explain_quantity(
            equipment_id=info["equipment_id"],
            equipment_name=info["equipment_name"],
            total_quantity=info["quantity_total"],
            available_quantity=info["available_quantity"],
            requested_quantity=plan.quantity,
            unit=info["unit"],
            has_date_range=bool(plan.needed_from and plan.needed_to),
        )
        res_text = f"{explanation}\n- **Vị trí lưu trữ:** {info['location']}"
        if info.get("has_inconsistency") and info.get("inconsistency_note"):
            res_text += f"\n\n{info['inconsistency_note']}"
        return res_text

    def _handle_quantity_sufficiency(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "check_quantity_sufficiency"
        eq_id = plan.entity_id
        if not eq_id:
            if state.active_equipment:
                eq_id = state.active_equipment.get("EquipmentID")
            elif state.active_equipment_ids:
                eq_id = state.active_equipment_ids[0]

        if not eq_id:
            return "Bạn muốn kiểm tra tính đáp ứng số lượng của thiết bị nào?"

        info = self.tools.get_equipment_count(eq_id)
        if not info.get("found"):
            return f"Không tìm thấy thiết bị có mã `{eq_id}` trong kho."

        state.active_equipment = {
            "EquipmentID": info["equipment_id"],
            "EquipmentName": info["equipment_name"],
            "Quantity": info["quantity_total"],
            "Location": info["location"],
        }
        state.active_equipment_ids = [info["equipment_id"]]

        req_qty = plan.quantity or 1
        has_date_range = bool(plan.needed_from and plan.needed_to)
        avail_qty = info["available_quantity"]
        if has_date_range:
            avail_info = self.tools.check_availability(eq_id, plan.needed_from, plan.needed_to)
            avail_qty = avail_info.get("available_quantity", avail_qty)

        return NumericExplanation.explain_sufficiency(
            equipment_id=info["equipment_id"],
            equipment_name=info["equipment_name"],
            total_quantity=info["quantity_total"],
            available_quantity=avail_qty,
            requested_quantity=req_qty,
            unit=info["unit"],
            has_date_range=has_date_range,
        )

    def _handle_equipment_detail(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_equipment_detail"
        eq_id = plan.entity_id or (state.active_equipment.get("EquipmentID") if state.active_equipment else None)
        if not eq_id and state.active_equipment_ids:
            eq_id = state.active_equipment_ids[0]

        if not eq_id:
            search_query = plan.entity_name or " ".join(plan.constraints.keywords)
            clean_search = re.sub(r"^(?:cho\s+)?(?:mình|em|tôi)?\s*(?:xem|hỏi)?\s*", "", search_query or "", flags=re.IGNORECASE).strip()
            if clean_search:
                matches = self.tools.search_equipment(plan.constraints, query=clean_search)
                if len(matches) == 1:
                    eq = matches[0]
                    eq_id = eq.equipment_id
                elif len(matches) > 1:
                    serialized_results = [_to_dict(r) for r in matches]
                    state_manager.set_result_set(state, serialized_results, result_type="equipment", page=1, page_size=15)
                    lines = [f"📋 Tìm thấy **{len(matches)}** thiết bị phù hợp với '{clean_search}':\n"]
                    for idx, it in enumerate(matches[:15], 1):
                        lines.append(f"{idx}. **{it.equipment_name}** (`{it.equipment_id}`) — Vị trí: {it.location} | Số lượng: {it.quantity_total} {it.unit or 'cái'}")
                    return "\n".join(lines)
                elif len(matches) == 0:
                    return f"Không tìm thấy thiết bị nào phù hợp với '{clean_search}' trong cơ sở dữ liệu."

        if not eq_id:
            return "Bạn muốn xem thông tin của thiết bị nào? Vui lòng cung cấp mã hoặc tên thiết bị."

        eq = self.tools.get_equipment_detail(eq_id)
        if not eq:
            return f"Không tìm thấy thiết bị có mã `{eq_id}` trong cơ sở dữ liệu."

        state.active_equipment = _to_dict(eq)
        state.active_equipment_ids = [eq.equipment_id]

        # Specific question detection: e.g. "ở đâu", "vị trí nào"
        lower_msg = plan.raw_message.lower()
        if any(w in lower_msg for w in ["ở đâu", "vị trí", "nằm ở đâu", "tủ nào"]):
            return f"📍 Thiết bị **{eq.equipment_name}** (`{eq.equipment_id}`) hiện đang được lưu trữ tại: **{eq.location or 'Chưa xác định'}**."

        return (
            f"**Thông tin thiết bị {eq.equipment_name}** (`{eq.equipment_id}`):\n"
            f"- **Phân loại:** {eq.category or 'Chưa phân loại'}\n"
            f"- **Vị trí lưu kho:** {eq.location or 'Chưa xác định'}\n"
            f"- **Tổng số lượng:** {eq.quantity_total} {eq.unit or 'cái'}\n"
            f"- **Mô tả kỹ thuật:** {eq.description or 'Không có mô tả'}"
        )

    def _handle_availability_query(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "check_availability"
        eq_id = plan.entity_id or (state.active_equipment.get("EquipmentID") if state.active_equipment else None)

        if not eq_id:
            query_text = plan.entity_name or " ".join(plan.constraints.keywords)
            if query_text:
                matches = self.tools.search_equipment(plan.constraints, query=query_text)
                if len(matches) == 1:
                    eq_id = matches[0].equipment_id
                elif len(matches) > 1:
                    for m in matches:
                        if m.equipment_name.lower().strip() == query_text.lower().strip():
                            eq_id = m.equipment_id
                            break
                    if not eq_id:
                        eq_id = matches[0].equipment_id

        if not eq_id:
            return "Bạn muốn kiểm tra tính khả dụng của thiết bị nào?"

        count_info = self.tools.get_equipment_count(eq_id)
        if not count_info.get("found"):
            return f"Không tìm thấy thiết bị có mã `{eq_id}` trong kho."

        state.active_equipment = {
            "EquipmentID": count_info["equipment_id"],
            "EquipmentName": count_info["equipment_name"],
            "Quantity": count_info["quantity_total"],
            "Location": count_info["location"],
        }
        state.active_equipment_ids = [count_info["equipment_id"]]

        eq_name = count_info.get("equipment_name", eq_id)
        total_qty = count_info.get("quantity_total", 0)
        borrowed_qty = count_info.get("borrowed_quantity", 0)
        approved_qty = count_info.get("approved_quantity", 0)
        avail_now = count_info.get("available_quantity", 0)
        unit = count_info.get("unit", "cái")
        location = count_info.get("location", "N/A")

        lower_msg = plan.raw_message.lower()
        asks_usage = any(w in lower_msg for w in [
            "ai sử dụng", "ai dùng", "đang được ai sử dụng", "có ai dùng", "có ai mượn", "ai đang mượn"
        ])

        req_qty = plan.quantity
        if not req_qty:
            m_qty = re.search(r"(?:tầm|khoảng|cỡ|mượn|cần)?\s*(\d+)\s*(?:cái|chiếc|con|bộ)?", lower_msg)
            if m_qty:
                try:
                    val = int(m_qty.group(1))
                    if 0 < val < 10000:
                        req_qty = val
                except ValueError:
                    pass

        asks_sufficiency = (req_qty is not None) or any(w in lower_msg for w in ["còn dư", "đủ không", "có đủ", "còn đủ", "đáp ứng đủ"])

        if asks_usage or asks_sufficiency:
            lines = [f"🔍 **Thông tin khả dụng & sử dụng thiết bị {eq_name}** (`{eq_id}`):\n"]

            if borrowed_qty > 0:
                lines.append(f"• **Tình trạng sử dụng:** Hiện đang có **{borrowed_qty} {unit}** được mượn và đang sử dụng trong các dự án.")
            else:
                lines.append(f"• **Tình trạng sử dụng:** Hiện tại **không có ai đang sử dụng** thiết bị này (chưa có đơn đang mượn).")

            lines.append(f"• **Tồn kho hiện tại:** Tổng cộng **{total_qty} {unit}** (Vị trí: **{location}**).")
            lines.append(f"• **Số lượng khả dụng:** **{avail_now} {unit}** (đã trừ {borrowed_qty} đang mượn và {approved_qty} đã duyệt).")

            if req_qty:
                if avail_now >= req_qty:
                    lines.append(
                        f"\n✅ **Khả năng đáp ứng:** Kho **hoàn toàn còn dư đủ** để bạn mượn **{req_qty} {unit}** "
                        f"({avail_now} {unit} khả dụng > {req_qty} {unit} yêu cầu)."
                    )
                else:
                    shortage = req_qty - avail_now
                    lines.append(
                        f"\n⚠️ **Khả năng đáp ứng:** Kho hiện **không đủ** {req_qty} {unit} "
                        f"(chỉ còn {avail_now} {unit} khả dụng, thiếu {shortage} {unit})."
                    )

            return "\n".join(lines)

        needed_from = plan.needed_from or "2026-01-01"
        needed_to = plan.needed_to or "2026-12-31"

        avail = self.tools.check_availability(eq_id, needed_from, needed_to)
        return (
            f"Tính khả dụng của thiết bị **{eq_name}** (`{eq_id}`) (từ {needed_from} đến {needed_to}):\n"
            f"- Tổng số lượng: {avail['quantity_total']}\n"
            f"- Số lượng đã cam kết: {avail['committed_quantity']}\n"
            f"- Số lượng khả dụng: **{avail['available_quantity']}**\n"
            f"- Đơn trùng lịch chờ duyệt: {len(avail.get('competing_pending_requests', []))}"
        )

    def _handle_alternative_search(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "search_alternative_equipment"
        target_id = plan.entity_id or (state.active_equipment.get("EquipmentID") if state.active_equipment else None)
        target_name = plan.entity_name or (state.active_equipment.get("EquipmentName") if state.active_equipment else None)

        if not target_id and not target_name:
            return "Bạn muốn tìm thiết bị thay thế cho thiết bị nào? Vui lòng cung cấp mã thiết bị (ví dụ: `TU2-007`) hoặc tên thiết bị."

        result = self.tools.search_alternative_equipment(target_equipment_id=target_id, target_equipment_name=target_name)
        if not result.get("success"):
            return f"Không thể tìm kiếm thiết bị thay thế: {result.get('message', 'Lỗi không xác định')}"

        alternatives = result.get("alternatives", [])
        if not alternatives:
            return f"Không tìm thấy thiết bị thay thế tiềm năng nào trong kho cho `{target_id or target_name}` ({result.get('target_name', '')})."

        trace.tool_result_count = len(alternatives)
        lines = [
            f"🔍 **Báo cáo đối soát thiết bị thay thế tiềm năng cho `{result.get('target_equipment_id') or target_name}` ({result.get('target_name')}):**\n",
            f"*{result.get('official_equivalence_notice', '')}*\n",
        ]

        # Group alternatives
        interchangeable = [a for a in alternatives if a.get("is_interchangeable")]
        accessories = [a for a in alternatives if a.get("compatibility_status") == "ACCESSORY_NOT_SUBSTITUTE"]
        unverified = [a for a in alternatives if not a.get("is_interchangeable") and a.get("compatibility_status") != "ACCESSORY_NOT_SUBSTITUTE"]

        if interchangeable:
            lines.append("📌 **Thiết bị cùng chức năng có tiềm năng thay thế:**")
            for alt in interchangeable:
                eq = alt["equipment"]
                lbl = alt.get("display_label") or alt["suitability_label"]
                lines.append(
                    f"• **{eq.equipment_name}** (`{eq.equipment_id}`): "
                    f"Đánh giá: **{lbl}** (Độ tương đồng mô tả: {alt['score']}/100)\n"
                    f"  - **Vị trí:** {eq.location or 'Chưa rõ'} | **Số lượng:** {eq.quantity_total} {eq.unit or 'cái'}\n"
                    f"  - **Ghi chú kỹ thuật:** {alt['technical_note']}"
                )
                if alt.get("matched_specs"):
                    lines.append(f"  - **Thông số khớp:** {', '.join(alt['matched_specs'])}")
                if alt.get("unverified_specs"):
                    lines.append(f"  - **Cần kiểm tra thêm (Datasheet):** {', '.join(alt['unverified_specs'])}")
            lines.append("")

        if accessories:
            lines.append("⚠️ **Phụ kiện liên quan (KHÔNG THỂ thay thế thiết bị chính):**")
            for alt in accessories:
                eq = alt["equipment"]
                lbl = alt.get("display_label") or alt["suitability_label"]
                lines.append(
                    f"• **{eq.equipment_name}** (`{eq.equipment_id}`): "
                    f"*{lbl}* — {alt['technical_note']} (Vị trí: {eq.location or 'Chưa rõ'})"
                )
            lines.append("")

        if unverified:
            lines.append("ℹ️ **Thiết bị khác nhóm / Chưa xác minh:**")
            for alt in unverified:
                eq = alt["equipment"]
                lbl = alt.get("display_label") or alt["suitability_label"]
                lines.append(
                    f"• **{eq.equipment_name}** (`{eq.equipment_id}`): "
                    f"*{lbl}* — {alt['technical_note']}"
                )

        return "\n".join(lines).strip()

    def _handle_external_sourcing(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "external_sourcing_search"
        query = plan.entity_name or plan.entity_id or plan.raw_message
        result = self.tools.external_sourcing_search(query)
        trace.tool_result_count = len(result.get("candidates", []))
        return result.get("message", "Tính năng tìm kiếm nguồn cung ngoài hiện chưa sẵn sàng.")

    def _handle_project_usage(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_equipment_project_usage"
        eq_id = plan.entity_id or (state.active_equipment.get("EquipmentID") if state.active_equipment else None)
        if not eq_id:
            return "Bạn muốn kiểm tra dự án sử dụng cho thiết bị nào? Vui lòng cung cấp mã thiết bị."

        usage_info = self.tools.get_equipment_project_usage(eq_id)
        if not usage_info.get("is_borrowed"):
            return (
                f"Hiện tại không có đơn mượn nào đang mượn thiết bị `{eq_id}` (**{usage_info.get('equipment_name', '')}**).\n"
                f"*(Lưu ý: Hệ thống hiện tại chỉ theo dõi qua các đơn mượn đã phê duyệt, "
                f"chưa hỗ trợ định vị thiết bị thời gian thực theo từng dự án)*"
            )

        records = usage_info.get("usage_records", [])
        trace.tool_result_count = len(records)
        lines = [f"Danh sách các đơn mượn/dự án đang sử dụng thiết bị `{eq_id}` (**{usage_info.get('equipment_name', '')}**):\n"]
        for r in records:
            lines.append(f"- Dự án **{r['project']}** (Người mượn: {r['requester']}, SL: {r['quantity']}, từ {r['needed_from']} đến {r['needed_to']})")
        return "\n".join(lines)

    def _handle_usage_query(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        lower_msg = plan.raw_message.lower()
        if any(w in lower_msg for w in ["dự án", "project", "ai đang dùng", "ai mượn", "ai giữ"]):
            return self._handle_project_usage(plan, state, trace)

        trace.selected_tool = "equipment_availability_schedule"
        eq_id = plan.entity_id or (state.active_equipment.get("EquipmentID") if state.active_equipment else None)
        if not eq_id:
            return "Bạn muốn hỏi thời gian nhận lại/trả của thiết bị nào?"

        res = self.tools.equipment_availability_schedule(eq_id)
        return res.get("message", "Đã tra cứu thời gian hoàn trả.")

    def _handle_schedule_planning(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        lower_msg = plan.raw_message.lower()
        if any(p in lower_msg for p in ["sắp xếp lịch", "điều phối", "xếp lịch", "tối ưu hóa", "sắp xếp lại"]):
            trace.response_mode = "unsupported"
            return (
                "Hệ thống quản lý kho V1 hiện tại chưa hỗ trợ tính năng tự động tối ưu hóa và sắp xếp lại lịch mượn giữa các dự án. "
                "Khi xảy ra xung đột lịch mượn thiết bị, Quản lý (Manager) sẽ xem xét mức độ ưu tiên của từng dự án để đưa ra quyết định phê duyệt."
            )

        trace.selected_tool = "equipment_availability_schedule"
        eq_id = plan.entity_id or (state.active_equipment.get("EquipmentID") if state.active_equipment else None)
        if eq_id:
            res = self.tools.equipment_availability_schedule(eq_id)
            return res.get("message", "Đã tra cứu thông tin lịch mượn.")

        trace.response_mode = "unsupported"
        return (
            "Hệ thống quản lý kho V1 hiện tại chưa hỗ trợ tính năng tự động tối ưu hóa và sắp xếp lại lịch mượn giữa các dự án. "
            "Khi xảy ra xung đột lịch mượn thiết bị, Quản lý (Manager) sẽ xem xét mức độ ưu tiên của từng dự án để đưa ra quyết định phê duyệt."
        )

    def _handle_condition_query(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.response_mode = "unsupported"
        eq_id = plan.entity_id or (state.active_equipment.get("EquipmentID") if state.active_equipment else "thiết bị")
        return (
            f"Hệ thống hiện tại chưa hỗ trợ theo dõi tình trạng hao mòn hay tiếp nhận báo hỏng thiết bị `{eq_id}` sau khi hoàn trả. "
            f"Tính năng này dự kiến sẽ được phát triển trong các phiên bản tiếp theo. Nếu phát hiện hư hỏng, bạn vui lòng thông báo trực tiếp cho Quản lý kho."
        )

    def _handle_request_create(
        self,
        plan: QueryPlan,
        state: ConversationState,
        user: SessionData,
        trace: AgentTrace,
    ) -> tuple[str, Optional[dict[str, Any]]]:
        trace.selected_tool = "create_borrow_request"
        eq_id = plan.entity_id

        # Check if user message specifies an equipment name or search keywords
        search_query = plan.entity_name or " ".join(plan.constraints.keywords)
        clean_search = re.sub(
            r"^(?:vậy\s+)?(?:cho\s+)?(?:mình|tôi|em)?\s*(?:muốn|cần|hãy)?\s*(?:tạo\s*đơn|lập\s*đơn|đăng\s*ký)?\s*mượn\s*",
            "",
            search_query or "",
            flags=re.IGNORECASE,
        ).strip()
        meaningful_tokens = [
            t for t in re.findall(r"[A-Za-z0-9_À-ỹ]+", clean_search.lower())
            if t not in {
                "nó", "này", "đó", "món", "thiết", "bị", "nếu", "chỉ", "thôi", "thì", "sao",
                "cho", "mình", "tôi", "em", "được", "không", "ạ", "nhé", "vậy", "tạo", "đơn",
                "lập", "đăng", "ký", "đi", "hãy", "giúp", "với"
            }
        ]
        has_genuine_search = bool(meaningful_tokens and len(" ".join(meaningful_tokens)) >= 2)

        # If user explicitly specified a target equipment, search it first!
        # Do NOT inherit stale active_equipment from prior turns!
        if not eq_id and has_genuine_search:
            clean_search = " ".join(meaningful_tokens)
            matches = self.tools.search_equipment(plan.constraints, query=clean_search)
            if len(matches) == 1:
                eq_id = matches[0].equipment_id
            elif len(matches) > 1:
                serialized_results = [_to_dict(r) for r in matches]
                state_manager.set_result_set(state, serialized_results, result_type="equipment", page=1, page_size=15)
                state.pending_action = "borrow_select"
                state.pending_form = PendingForm(
                    equipment_id="",
                    equipment_name="",
                    quantity=plan.quantity or 1,
                    needed_from=plan.needed_from,
                    needed_to=plan.needed_to,
                    project=plan.project or "",
                    purpose=plan.purpose or "",
                )
                lines = [f"Tôi tìm thấy **{len(matches)}** thiết bị phù hợp với '{clean_search}' trong kho:\n"]
                for idx, c in enumerate(matches[:10], 1):
                    lines.append(
                        f"{idx}. **{c.equipment_name}** (`{c.equipment_id}`) — "
                        f"Vị trí: {c.location} | Số lượng: {c.quantity_total} {c.unit or 'cái'}"
                    )
                lines.append("\n*(Vui lòng chọn thiết bị bằng cách nhắn 'cái thứ 1', 'cái thứ 2' hoặc mã thiết bị để tiếp tục)*")
                return ("\n".join(lines), None)
            elif len(matches) == 0:
                return (
                    f"Không tìm thấy thiết bị nào phù hợp với '{clean_search}' trong kho để tạo yêu cầu mượn. "
                    f"Bạn vui lòng kiểm tra lại tên hoặc đặc tính thiết bị.",
                    None,
                )

        # Only fall back to pending form or active context if NO new search query was provided
        if not eq_id:
            if state.pending_form and state.pending_form.equipment_id:
                eq_id = state.pending_form.equipment_id
            elif state.active_equipment and state.pending_action != "borrow_select":
                eq_id = state.active_equipment.get("EquipmentID")
            elif state.active_equipment_ids and state.pending_action != "borrow_select":
                eq_id = state.active_equipment_ids[0]

        if not eq_id:
            action = {
                "type": "show_borrow_form",
                "prefill": {
                    "equipment_id": "",
                    "equipment_name": "",
                    "project": plan.project or "",
                },
            }
            reply = "Tôi đã mở biểu mẫu đăng ký mượn thiết bị bên dưới. Vui lòng chọn thiết bị và điền thông tin chi tiết."
            return (reply, action)

        state.pending_action = None
        eq = self.tools.get_equipment_detail(eq_id)
        eq_name = eq.equipment_name if eq else (state.active_equipment.get("EquipmentName") if state.active_equipment else eq_id)

        # Never leak or default project across unrelated requests
        proj_val = plan.project or (state.pending_form.project if (state.pending_form and state.pending_form.project) else "")

        state.pending_form = PendingForm(
            equipment_id=eq_id,
            equipment_name=eq_name,
            quantity=plan.quantity or (state.pending_form.quantity if state.pending_form and state.pending_form.quantity else 1),
            needed_from=plan.needed_from or (state.pending_form.needed_from if state.pending_form else None),
            needed_to=plan.needed_to or (state.pending_form.needed_to if state.pending_form else None),
            project=proj_val,
            purpose=plan.purpose or (state.pending_form.purpose if state.pending_form and state.pending_form.purpose else ""),
        )

        # Check shortage if quantity provided and eq exists
        shortage_note = ""
        if eq and state.pending_form.quantity:
            if state.pending_form.quantity > eq.quantity_total:
                shortage = state.pending_form.quantity - eq.quantity_total
                shortage_note = f"\n⚠️ *Lưu ý: Kho hiện ghi nhận {eq.quantity_total} cái {eq.equipment_id}, thấp hơn số lượng yêu cầu {state.pending_form.quantity} cái (thiếu {shortage} cái).*"

        # Reminder if user asked AI to auto-approve
        auto_approve_notice = ""
        if plan.ask_auto_approve:
            auto_approve_notice = (
                "\n\n⚠️ *Lưu ý: Trợ lý AI không có quyền tự phê duyệt đơn mượn. "
                "Yêu cầu của bạn sau khi tạo sẽ được Quản lý (Manager) xem xét và phê duyệt theo đúng quy trình.*"
            )

        action = {
            "type": "show_borrow_form",
            "prefill": {
                "equipment_id": state.pending_form.equipment_id,
                "equipment_name": state.pending_form.equipment_name,
                "quantity": state.pending_form.quantity,
                "needed_from": state.pending_form.needed_from,
                "needed_to": state.pending_form.needed_to,
                "project": state.pending_form.project,
                "purpose": state.pending_form.purpose,
            },
        }

        reply = (
            f"Tôi đã mở biểu mẫu mượn thiết bị **{state.pending_form.equipment_name}** (`{state.pending_form.equipment_id}`)."
            f"{shortage_note}{auto_approve_notice}\nBạn vui lòng kiểm tra lại thông tin và xác nhận gửi yêu cầu."
        )
        return (reply, action)

    def _handle_my_requests(
        self,
        plan: QueryPlan,
        user: SessionData,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "list_my_requests"
        target_email = user.user_email
        target_name_display = "của bạn"
        requests = []

        if plan.entity_name:
            searched_name = plan.entity_name.lower().strip()
            user_name_lower = (user.user_name or "").lower().strip()
            searched_tokens = set(re.findall(r"[A-Za-zÀ-ỹ]+", searched_name))
            user_tokens = set(re.findall(r"[A-Za-zÀ-ỹ]+", user_name_lower))
            is_same_user = (
                searched_name in user_name_lower
                or user_name_lower in searched_name
                or (len(searched_tokens & user_tokens) >= 2)
                or (len(searched_tokens) == 1 and searched_tokens.issubset(user_tokens))
            )
            if is_same_user:
                target_email = user.user_email
                requests = self.tools.list_my_requests(target_email, status=plan.status_filter)
            elif not user.is_manager and not user.is_admin:
                trace.tool_arguments = {"user_email": user.user_email, "target_person": plan.entity_name}
                return (
                    f"Bạn chỉ có quyền xem các thiết bị do chính mình mượn. "
                    f"Để tra cứu thông tin mượn thiết bị của nhân sự khác ({plan.entity_name}), bạn cần có quyền Quản lý (Manager)."
                )
            else:
                all_reqs = self.tools.request_repo.list_all(status=plan.status_filter)
                requests = [
                    r for r in all_reqs
                    if searched_name in (r.requester_name or "").lower()
                ]
                target_name_display = f"của {plan.entity_name}"
        else:
            requests = self.tools.list_my_requests(target_email, status=plan.status_filter)

        trace.tool_arguments = {"user_email": target_email, "status": plan.status_filter}
        trace.tool_result_count = len(requests)
        trace.tool_result_type = "user_requests"
        trace.response_type = "table"

        serialized = [_to_dict(r) for r in requests]
        state_manager.set_result_set(
            state,
            serialized,
            result_type="user_requests",
            page=1,
            page_size=10,
            result_schema="user_requests",
        )
        state.last_intent = IntentType.MY_REQUESTS

        if not requests:
            if plan.status_filter == "Approved":
                return f"Không có yêu cầu mượn nào {target_name_display} ở trạng thái Đã duyệt (Approved)."
            elif plan.status_filter == "Pending":
                return f"Không có yêu cầu mượn nào {target_name_display} đang chờ duyệt (Pending)."
            elif plan.status_filter == "Borrowed":
                return f"Hiện tại không có thiết bị nào {target_name_display} đang trong trạng thái mượn (Borrowed)."
            elif plan.status_filter == "Rejected":
                return f"Không có yêu cầu mượn nào {target_name_display} bị từ chối (Rejected)."
            return f"Chưa có yêu cầu mượn thiết bị nào {target_name_display} trong hệ thống."

        unique_eq_types = set(r.equipment_id for r in requests)
        total_borrowed_qty = sum(r.quantity for r in requests)

        # Check follow-up list query: "Những thiết bị đó là gì"
        is_list_detail_query = any(p in plan.raw_message.lower() for p in [
            "những thiết bị đó là gì", "các thiết bị đó là gì", "thiết bị đó là gì",
            "gồm những thiết bị nào", "những món đó là gì", "cụ thể là những thiết bị nào"
        ])
        if is_list_detail_query:
            lines = [f"📦 **Danh sách cụ thể các thiết bị đang mượn {target_name_display}** ({len(requests)} đơn, {len(unique_eq_types)} loại thiết bị):\n"]
            for r in requests:
                req_id_str = getattr(r, "request_id", None) or getattr(r, "display_id", None) or f"REQ-{r.id:06d}"
                eq_name = r.equipment_name or r.equipment_id
                lines.append(
                    f"• **{eq_name}** (`{r.equipment_id}`): **{r.quantity}** cái | Dự án: **{r.project or 'N/A'}** | Mã đơn: `{req_id_str}`"
                )
            return "\n".join(lines)

        status_label = ""
        if plan.status_filter == "Approved":
            status_label = " đã được duyệt"
        elif plan.status_filter == "Pending":
            status_label = " đang chờ duyệt"
        elif plan.status_filter == "Borrowed":
            status_label = " đang mượn"
        elif plan.status_filter == "Rejected":
            status_label = " bị từ chối"

        if plan.status_filter == "Borrowed":
            summary_header = (
                f"📋 Hiện tại bạn đang có **{len(requests)} đơn mượn** với **{len(unique_eq_types)} loại thiết bị** khác nhau "
                f"(tổng cộng **{total_borrowed_qty}** đơn vị/cái) đang trong trạng thái mượn (Borrowed):\n"
            )
        else:
            summary_header = f"📋 **Các yêu cầu mượn thiết bị{status_label} {target_name_display}** ({len(requests)} yêu cầu):\n"

        lines = [
            summary_header,
            "| Mã YC | Thiết bị | Dự án | SL | Ngày mượn | Ngày trả | Mức ưu tiên | Trạng thái |",
            "| :--- | :--- | :--- | :---: | :---: | :---: | :--- | :--- |",
        ]
        for r in requests[:10]:
            req_id_str = getattr(r, "request_id", None) or getattr(r, "display_id", None) or f"REQ-{r.id:06d}"
            eq_name = r.equipment_name or r.equipment_id
            eq_display = f"`{r.equipment_id}` ({eq_name})" if r.equipment_name else f"`{r.equipment_id}`"
            prio = r.final_priority_level or r.priority_level or "Needs review"
            n_from = (r.needed_from or "")[:10]
            n_to = (r.needed_to or "")[:10]

            id_cell = escape_markdown_cell(req_id_str, wrap_code=True)
            eq_cell = escape_markdown_cell(eq_display)
            proj_cell = escape_markdown_cell(r.project or "N/A")
            qty_cell = escape_markdown_cell(r.quantity)
            from_cell = escape_markdown_cell(n_from)
            to_cell = escape_markdown_cell(n_to)
            prio_cell = escape_markdown_cell(prio)
            status_cell = escape_markdown_cell(r.status)

            lines.append(
                f"| {id_cell} | {eq_cell} | {proj_cell} | {qty_cell} | {from_cell} | {to_cell} | {prio_cell} | {status_cell} |"
            )
        return "\n".join(lines)

    # -------------------------------------------------------------
    # Manager Handlers
    # -------------------------------------------------------------

    def _handle_pending_request_count(self, user: SessionData, trace: AgentTrace) -> str:
        trace.selected_tool = "count_pending_requests"
        if not user.is_manager and not user.is_admin:
            user_pending = [r for r in self.tools.list_my_requests(user.user_email) if (r.status or "").lower() == "pending"]
            cnt = len(user_pending)
            if cnt == 0:
                return "Hiện bạn không có đơn mượn nào đang chờ duyệt."
            return f"Hiện bạn đang có **{cnt}** đơn mượn đang chờ quản lý phê duyệt."

        counts = self.tools.count_pending_requests(user.user_email)
        total = counts["total_pending"]
        actionable = counts["actionable_pending"]
        self_cnt = counts["self_pending"]

        if total == 0 or actionable == 0:
            if self_cnt > 0:
                return f"Hiện không có đơn nào đang chờ bạn duyệt ({self_cnt} đơn chờ duyệt do chính bạn tạo cần quản lý khác duyệt)."
            return "Hiện không có đơn nào đang chờ bạn duyệt."

        if self_cnt > 0:
            return (
                f"Hiện có tổng cộng **{total}** đơn đang chờ phê duyệt:\n"
                f"- **{actionable}** đơn từ nhân viên khác đang chờ bạn phê duyệt.\n"
                f"- **{self_cnt}** đơn do chính bạn tạo (cần một quản lý khác phê duyệt theo quy định)."
            )
        return f"Hiện có **{actionable}** đơn mượn đang chờ bạn phê duyệt."

    def _handle_pending_request_list(
        self,
        user: SessionData,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "list_pending_requests"
        if not user.is_manager and not user.is_admin:
            user_pending = [r for r in self.tools.list_my_requests(user.user_email) if (r.status or "").lower() == "pending"]
            if not user_pending:
                return "Hiện bạn không có đơn mượn nào đang chờ duyệt."
            serialized = [_to_dict(r) for r in user_pending]
            state_manager.set_result_set(state, serialized, result_type="request", page=1, page_size=10)
            lines = [f"📋 Danh sách **{len(user_pending)}** đơn mượn của bạn đang chờ phê duyệt:\n"]
            for i, r in enumerate(user_pending[:10], 1):
                lines.append(
                    f"{i}. **Đơn #{r.id}** - Thiết bị: `{r.equipment_id}` ({r.equipment_name}) | SL: {r.quantity}\n"
                    f"   - Dự án: {r.project} | Thời gian: {r.needed_from} đến {r.needed_to} | Trạng thái: **{r.status}**"
                )
            return "\n".join(lines)

        pending = self.tools.list_pending_requests(user.user_email)
        if not pending:
            return "Hiện không có đơn mượn nào đang chờ duyệt."

        serialized = [_to_dict(r) for r in pending]
        state_manager.set_result_set(state, serialized, result_type="request", page=1, page_size=10)

        lines = [f"Danh sách **{len(pending)}** đơn đang chờ phê duyệt:\n"]
        for i, r in enumerate(pending[:10], 1):
            is_self = (r.requester_email or "").lower() == user.user_email.lower()
            tag = " *(Đơn của bạn)*" if is_self else ""
            lines.append(
                f"{i}. **Đơn #{r.id}**{tag} - Người mượn: **{r.requester_name}**\n"
                f"   - Thiết bị: `{r.equipment_id}` ({r.equipment_name}) | SL: {r.quantity}\n"
                f"   - Dự án: {r.project} | Ưu tiên AI: **{r.priority_level}**\n"
                f"   - Thời gian: {r.needed_from} đến {r.needed_to}"
            )
        return "\n".join(lines)

    def _handle_recent_request(
        self,
        user: SessionData,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_recent_request"
        req = self.tools.get_most_recent_request()
        if not req:
            return "Hiện tại hệ thống chưa ghi nhận yêu cầu mượn thiết bị nào."

        state.active_request = _to_dict(req)
        state.active_request_ids = [req.id]
        state_manager.set_result_set(state, [_to_dict(req)], result_type="request", page=1, page_size=1)

        return (
            f"Yêu cầu gần đây nhất là:\n\n"
            f"• **Người gửi:** {req.requester_name} ({req.requester_email or 'không rõ email'})\n"
            f"• **Thiết bị:** {req.equipment_name} (`{req.equipment_id}`)\n"
            f"• **Dự án:** {req.project}\n"
            f"• **Số lượng:** {req.quantity} cái\n"
            f"• **Ngày mượn:** {req.needed_from}\n"
            f"• **Ngày trả:** {req.needed_to}\n"
            f"• **Trạng thái:** **{req.status}**"
        )

    def _handle_recent_requests(
        self,
        plan: QueryPlan,
        user: SessionData,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_recent_requests"
        if plan.is_group_reference and state.last_result_set and state.last_result_type in ["request", "overdue_loans", "active_loans"]:
            items = state.last_result_set
            lines = [
                f"📋 Danh sách **{len(items)}** yêu cầu mượn thiết bị trong phiên truy vấn:\n",
                "| Mã đơn | Người gửi | Thiết bị | Dự án | Ngày mượn | Ngày trả | Trạng thái |",
                "|---|---|---|---|---|---|---|",
            ]
            for r in items:
                req_id = r.get("RequestID") or f"#{r.get('id', '')}"
                name = r.get("RequesterName") or r.get("borrower") or ""
                eq_id = r.get("EquipmentID") or r.get("equipment_id") or ""
                eq_name = r.get("EquipmentName") or r.get("equipment_name") or ""
                proj = r.get("Project") or r.get("project") or ""
                nf = r.get("NeededFrom") or r.get("needed_from") or ""
                nt = r.get("NeededTo") or r.get("needed_to") or ""
                st = r.get("Status") or r.get("status") or ""
                lines.append(f"| {req_id} | {name} | `{eq_id}` ({eq_name}) | {proj} | {nf} | {nt} | {st} |")
            return "\n".join(lines)

        limit = plan.quantity or 5
        reqs = self.tools.get_recent_requests(limit=limit)
        if not reqs:
            return "Hiện tại hệ thống chưa ghi nhận yêu cầu mượn thiết bị nào."

        serialized = [_to_dict(r) for r in reqs]
        state_manager.set_result_set(
            state,
            serialized,
            result_type="request",
            page=1,
            page_size=len(reqs),
            result_schema="recent_requests",
        )
        state.active_request = serialized[0]
        state.active_request_ids = [r.id for r in reqs]

        lines = [
            f"📋 Danh sách {len(reqs)} yêu cầu mượn thiết bị gần đây nhất:\n",
            "| Mã YC | Người gửi | Thiết bị | Dự án | Ngày tạo | Ngày mượn | Ngày trả | Trạng thái |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in reqs:
            c_date = (r.created_at or "")[:10]
            lines.append(
                f"| #{r.id} | {r.requester_name} | {r.equipment_id} ({r.equipment_name}) | {r.project} | {c_date} | {r.needed_from} | {r.needed_to} | {r.status} |"
            )
        return "\n".join(lines)

    def _handle_overdue_loans(
        self,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_overdue_loans"
        overdue_items = self.tools.get_overdue_loans()

        # Save complete result set to conversation state
        serialized_items = []
        for item in overdue_items:
            s_item = {k: v for k, v in item.items() if k != "request"}
            serialized_items.append(s_item)

        state_manager.set_result_set(
            state,
            serialized_items,
            result_type="overdue_loans",
            page=1,
            page_size=10,
            result_schema="overdue_loans",
        )
        trace.tool_result_count = len(serialized_items)

        if not overdue_items:
            return "Hiện tại không có thiết bị nào đang trong trạng thái mượn (Borrowed) bị quá hạn trả."

        lines = [
            f"⚠️ Tìm thấy **{len(overdue_items)}** lượt mượn thiết bị đang quá hạn trả:\n",
            "| Mã đơn | Người mượn | Thiết bị | Mã thiết bị | Dự án | Ngày mượn | Ngày trả | Quá hạn |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for item in overdue_items:
            req_id_str = item.get("RequestID") or f"#{item.get('id', '')}"
            lines.append(
                f"| {req_id_str} | {item['borrower']} | {item['equipment_name']} | `{item['equipment_id']}` | {item['project']} | {item['needed_from']} | {item['needed_to']} | {item['days_overdue']} ngày |"
            )
        return "\n".join(lines)

    def _handle_overdue_borrowers(
        self,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_overdue_borrowers"
        # 1. Resolve from preceding result set if available
        if state.last_result_type == "overdue_loans" and state.last_result_set:
            items = state.last_result_set
        else:
            overdue_items = self.tools.get_overdue_loans()
            items = [{k: v for k, v in it.items() if k != "request"} for it in overdue_items]

        if not items:
            return "Hiện tại không có người dùng nào đang giữ thiết bị quá hạn."

        # 2. Extract distinct borrowers and group details
        grouped: dict[str, dict[str, Any]] = {}
        for it in items:
            name = it.get("RequesterName") or it.get("borrower") or "Không rõ"
            email = it.get("RequesterEmail") or it.get("borrower_email") or ""
            key = email.lower() if email else name.lower()
            if key not in grouped:
                grouped[key] = {
                    "name": name,
                    "email": email,
                    "items": [],
                    "total_quantity": 0,
                    "max_overdue_days": 0,
                }
            eq_name = it.get("EquipmentName") or it.get("equipment_name") or ""
            eq_id = it.get("EquipmentID") or it.get("equipment_id") or ""
            days = it.get("days_overdue") or it.get("overdue_days") or 0
            qty = it.get("Quantity") or it.get("quantity") or 1
            project = it.get("Project") or it.get("project") or ""
            grouped[key]["items"].append({
                "equipment_id": eq_id,
                "equipment_name": eq_name,
                "days_overdue": days,
                "quantity": qty,
                "project": project,
            })
            grouped[key]["total_quantity"] += qty
            grouped[key]["max_overdue_days"] = max(grouped[key]["max_overdue_days"], days)

        borrower_list = list(grouped.values())
        trace.tool_result_count = len(borrower_list)

        # Update state with borrower list
        state_manager.set_result_set(
            state,
            borrower_list,
            result_type="active_borrowers",
            page=1,
            page_size=10,
            result_schema="borrower_list",
        )

        lines = [
            f"👥 Danh sách **{len(borrower_list)}** người dùng đang giữ thiết bị quá hạn (tổng cộng {len(items)} đơn quá hạn):\n",
            "| Người mượn | Email | Số đơn quá hạn | Tổng SL | Thiết bị & Số ngày quá hạn |",
            "|---|---|---|---|---|",
        ]
        for b in borrower_list:
            eq_details = ", ".join(
                f"`{x['equipment_id']}` (trễ {x['days_overdue']} ngày)"
                for x in b["items"]
            )
            email_display = b["email"] if b["email"] else "—"
            lines.append(
                f"| **{b['name']}** | {email_display} | {len(b['items'])} đơn | {b['total_quantity']} cái | {eq_details} |"
            )
        return "\n".join(lines)

    def _handle_active_loans(
        self,
        plan: QueryPlan,
        user: SessionData,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_active_loans"
        loans = self.tools.get_active_loans()

        target_person = plan.entity_name
        if target_person:
            searched_name = target_person.lower().strip()
            user_name_lower = (user.user_name or "").lower().strip()
            searched_tokens = set(re.findall(r"[A-Za-zÀ-ỹ]+", searched_name))
            user_tokens = set(re.findall(r"[A-Za-zÀ-ỹ]+", user_name_lower))
            is_same_user = (
                searched_name in user_name_lower
                or user_name_lower in searched_name
                or (len(searched_tokens & user_tokens) >= 2)
                or (len(searched_tokens) == 1 and searched_tokens.issubset(user_tokens))
            )

            if not user.is_manager and not user.is_admin and not is_same_user:
                return (
                    f"Bạn chỉ có quyền xem các thiết bị do chính mình mượn. "
                    f"Để tra cứu thông tin mượn thiết bị của nhân sự khác ({target_person}), bạn cần có quyền Quản lý (Manager)."
                )

            filtered = []
            for r in loans:
                r_name = (r.requester_name or "").lower()
                r_email = (r.requester_email or "").lower()
                r_tokens = set(re.findall(r"[A-Za-zÀ-ỹ]+", r_name))
                if (
                    searched_name in r_name
                    or searched_name in r_email
                    or (searched_tokens and searched_tokens.issubset(r_tokens))
                    or (len(searched_tokens & r_tokens) >= 2)
                    or (is_same_user and r_email == user.user_email.lower())
                ):
                    filtered.append(r)
            loans = filtered

            if not loans:
                return f"Hiện tại không có thiết bị nào đang được {target_person} mượn (Borrowed)."

        elif not user.is_manager and not user.is_admin:
            loans = [r for r in loans if (r.requester_email or "").lower() == user.user_email.lower()]
            if not loans:
                return "Hiện tại bạn không có thiết bị nào đang trong trạng thái mượn (Borrowed)."

        serialized = [_to_dict(r) for r in loans]
        state_manager.set_result_set(
            state,
            serialized,
            result_type="active_loans",
            page=1,
            page_size=10,
            result_schema="active_loans",
        )
        trace.tool_result_count = len(loans)

        if not loans:
            return "Hiện tại không có thiết bị nào đang trong trạng thái được mượn (Borrowed)."

        title_prefix = f"đang được {target_person} mượn" if target_person else "đang được mượn"
        lines = [
            f"📦 Danh sách **{len(loans)}** thiết bị {title_prefix}:\n",
            "| Mã đơn | Người mượn | Thiết bị | Mã thiết bị | Dự án | Ngày mượn | Ngày trả dự kiến |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in loans:
            req_id_str = getattr(r, "request_id", None) or getattr(r, "display_id", None) or f"#{r.id}"
            lines.append(
                f"| {req_id_str} | {r.requester_name} | {r.equipment_name} | `{r.equipment_id}` | {r.project} | {r.needed_from} | {r.needed_to} |"
            )
        return "\n".join(lines)

    def _handle_active_borrowers(
        self,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_active_borrowers"
        borrowers = self.tools.get_active_borrowers()
        state_manager.set_result_set(
            state,
            borrowers,
            result_type="active_borrowers",
            page=1,
            page_size=10,
            result_schema="active_borrowers",
        )
        trace.tool_result_count = len(borrowers)

        if not borrowers:
            return "Hiện tại không có người dùng nào đang giữ thiết bị (Borrowed) từ kho."

        lines = [
            f"👥 Danh sách **{len(borrowers)}** người dùng đang mượn thiết bị:\n",
            "| Người mượn | Số thiết bị đang mượn | Số đơn mượn | Chi tiết thiết bị |",
            "|---|---|---|---|",
        ]
        for b in borrowers:
            eq_summary = ", ".join(f"`{item['equipment_id']}` ({item['quantity']})" for item in b["equipment_items"])
            lines.append(
                f"| **{b['name']}** ({b['email']}) | {b['total_quantity']} cái | {b['request_count']} đơn | {eq_summary} |"
            )
        return "\n".join(lines)

    def _handle_active_borrowers_count(
        self,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_active_borrowers"
        borrowers = self.tools.get_active_borrowers()
        loans = self.tools.get_active_loans()
        state_manager.set_result_set(
            state,
            borrowers,
            result_type="active_borrowers",
            page=1,
            page_size=10,
            result_schema="active_borrowers",
        )
        trace.tool_result_count = len(borrowers)

        n_borrowers = len(borrowers)
        n_loans = len(loans)

        if n_borrowers == 0:
            return "Hiện không có người nào đang mượn thiết bị."

        return (
            f"Hiện có **{n_borrowers}** người đang mượn thiết bị, "
            f"tương ứng với **{n_loans}** lượt mượn đang hoạt động.\n\n"
            f"*(Bạn có thể nhắn 'Những người đó là ai?' để xem danh sách chi tiết.)*"
        )

    def _handle_active_loans_count(
        self,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_active_loans"
        loans = self.tools.get_active_loans()
        serialized = [_to_dict(r) for r in loans]
        state_manager.set_result_set(
            state,
            serialized,
            result_type="active_loans",
            page=1,
            page_size=10,
            result_schema="active_loans",
        )
        trace.tool_result_count = len(loans)

        n = len(loans)
        if n == 0:
            return "Hiện không có thiết bị nào đang trong trạng thái Borrowed."

        return (
            f"Hiện có **{n}** lượt mượn thiết bị đang hoạt động (Status = Borrowed).\n\n"
            f"*(Bạn có thể nhắn 'Thiết bị nào đang được mượn?' để xem danh sách chi tiết.)*"
        )

    def _handle_return_request(
        self,
        plan: QueryPlan,
        user: SessionData,
        state: ConversationState,
        trace: AgentTrace,
    ) -> tuple[str, Optional[dict[str, Any]]]:
        """Handle 'Mình muốn trả đồ' → return flow."""
        trace.selected_tool = "get_active_loans_for_user"

        active_loans = self.tools.get_active_loans_for_user(user.user_email)
        trace.tool_result_count = len(active_loans)

        if not active_loans:
            return (
                "Hiện hệ thống chưa ghi nhận thiết bị nào đang được bạn mượn (Status = Borrowed). "
                "Nếu bạn cho rằng đây là nhầm lẫn, vui lòng liên hệ quản lý.",
                None,
            )

        target_loan = None

        # 1. Target by request ID (direct in plan or resolved)
        if plan.target_request_id:
            matched = [r for r in active_loans if r.id == plan.target_request_id]
            if matched:
                target_loan = matched[0]

        # 2. Ordinal resolution: "Tôi muốn trả cái thứ 1" against last borrowed_loans result set
        if not target_loan and plan.ordinal_index is not None and state.last_result_type == "borrowed_loans" and state.last_result_set:
            item = state_manager.get_item_by_ordinal(state, plan.ordinal_index)
            if item:
                req_id = item.get("id") or item.get("request_id")
                if req_id:
                    matched = [r for r in active_loans if r.id == req_id]
                    if matched:
                        target_loan = matched[0]

        # 3. Equipment ID in message: "Tôi muốn trả TU1-001"
        if not target_loan and plan.entity_id:
            matched = [r for r in active_loans if r.equipment_id.upper() == plan.entity_id.upper()]
            if len(matched) == 1:
                target_loan = matched[0]
            elif len(matched) > 1:
                active_loans = matched

        # 4. Target by equipment Name / attributes / keywords: "Mình muốn trả Conn 4.2mm"
        if not target_loan:
            cand_name = plan.entity_name or " ".join(plan.constraints.keywords)
            clean_cand = re.sub(
                r"^(?:mình|tôi|em)?\s*(?:muốn|cần)?\s*trả\s*",
                "",
                cand_name or "",
                flags=re.IGNORECASE,
            ).strip()

            if clean_cand and len(clean_cand) >= 2:
                norm_cand = clean_cand.lower()
                tokens = [t for t in re.split(r"[\s\-_,]+", norm_cand) if t and t not in ["cái", "chiếc", "bộ", "đồ", "thiết", "bị"]]
                matched_by_name = []
                for r in active_loans:
                    r_text = f"{r.equipment_id} {r.equipment_name} {r.project}".lower()
                    if norm_cand in r_text:
                        matched_by_name.append(r)
                    elif tokens and all(t in r_text for t in tokens):
                        matched_by_name.append(r)
                    elif plan.constraints.size_mm and (f"{plan.constraints.size_mm}mm" in r_text or str(plan.constraints.size_mm) in r_text):
                        if all(k.lower() in r_text for k in plan.constraints.keywords if len(k) > 1):
                            matched_by_name.append(r)

                if len(matched_by_name) == 1:
                    target_loan = matched_by_name[0]
                elif len(matched_by_name) > 1:
                    active_loans = matched_by_name

        # 5. Exactly one active loan overall → auto-select
        if not target_loan and len(active_loans) == 1:
            target_loan = active_loans[0]

        # One loan found → open return form
        if target_loan:
            state.pending_action = None
            serialized_loans = [_to_dict(r) for r in active_loans]
            state_manager.set_result_set(
                state,
                serialized_loans,
                result_type="borrowed_loans",
                page=1,
                page_size=len(active_loans),
                result_schema="borrowed_loans",
            )
            state.active_request = _to_dict(target_loan)

            req_id_str = getattr(target_loan, "request_id", None) or getattr(target_loan, "display_id", None) or f"REQ-{target_loan.id:06d}"
            
            # Condition note and condition type prefill
            cond_note = plan.condition_notes or ""
            ret_cond = "Tốt"
            if cond_note:
                if any(k in cond_note.lower() for k in ["hỏng", "trầy", "xước", "vỡ", "lỗi", "cháy", "kém", "hao mòn"]):
                    ret_cond = "Khác"
                else:
                    ret_cond = "Tốt"

            ret_qty = plan.quantity if (plan.quantity and 1 <= plan.quantity <= target_loan.quantity) else target_loan.quantity

            action_payload = {
                "type": "show_return_form",
                "prefill": {
                    "request_id": target_loan.id,
                    "display_id": req_id_str,
                    "equipment_id": target_loan.equipment_id,
                    "equipment_name": target_loan.equipment_name,
                    "project": target_loan.project,
                    "quantity": ret_qty,
                    "needed_from": target_loan.needed_from,
                    "needed_to": target_loan.needed_to,
                    "return_condition": ret_cond,
                    "return_condition_note": cond_note,
                    "condition_notes": cond_note,
                },
            }

            qty_clarification = ""
            if target_loan.quantity > 1:
                qty_clarification = (
                    f" (Đơn đang mượn {target_loan.quantity} cái. "
                    f"Biểu mẫu đã mở sẵn {ret_qty} cái, bạn có thể điều chỉnh số lượng hoàn trả nếu trả từng phần)."
                )

            note_confirm = f"\n- Ghi chú tình trạng ghi nhận: *\"{cond_note}\"*" if cond_note else ""

            reply = (
                f"Tôi đã mở biểu mẫu trả thiết bị **{target_loan.equipment_name}** (`{target_loan.equipment_id}`) "
                f"thuộc dự án **{target_loan.project}**{qty_clarification}.{note_confirm}\n\n"
                f"Vui lòng kiểm tra lại thông tin và xác nhận hoàn trả:"
            )
            return (reply, action_payload)

        # Multiple loans → selection list
        state.pending_action = "return"
        serialized_loans = [_to_dict(r) for r in active_loans]
        state_manager.set_result_set(
            state,
            serialized_loans,
            result_type="borrowed_loans",
            page=1,
            page_size=len(active_loans),
            result_schema="borrowed_loans",
        )

        lines = [
            f"Bạn đang có **{len(active_loans)}** yêu cầu mượn đang hoạt động. "
            f"Vui lòng chọn thiết bị muốn trả:\n",
        ]
        for idx, r in enumerate(active_loans, 1):
            req_id_str = getattr(r, "request_id", None) or f"REQ-{r.id:06d}"
            lines.append(
                f"{idx}. **{r.equipment_name}** (`{r.equipment_id}`) — Dự án: {r.project} — {r.quantity} cái — Hạn trả: {r.needed_to}"
            )
        lines.append("\n*(Nhắn ví dụ: 'Tôi muốn trả cái thứ 1' để chọn thiết bị)*")
        return ("\n".join(lines), None)

    def _handle_schedule_conflicts(
        self,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_schedule_conflicts"
        state.last_result_type = "schedule_conflicts"
        conflicts = self.tools.get_schedule_conflicts()
        if not conflicts:
            state.last_result_set = []
            return "Hiện tại không có đơn mượn nào bị xung đột lịch trùng ngày."

        # Save to state for follow-up reference (e.g. "những người đó là ai")
        state.last_result_set = [
            {
                "pending_id": getattr(c["pending_request"], "id", None) or c["pending_request"].get("id"),
                "equipment_id": getattr(c["pending_request"], "equipment_id", None) or c["pending_request"].get("equipment_id"),
                "requester_name": getattr(c["pending_request"], "requester_name", None) or c["pending_request"].get("requester_name"),
                "requester_email": getattr(c["pending_request"], "requester_email", None) or c["pending_request"].get("requester_email"),
                "project": getattr(c["pending_request"], "project", None) or c["pending_request"].get("project"),
                "conflicting_requests": [
                    {
                        "id": getattr(o, "id", None) or o.get("id"),
                        "requester_name": getattr(o, "requester_name", None) or o.get("requester_name"),
                        "requester_email": getattr(o, "requester_email", None) or o.get("requester_email"),
                        "project": getattr(o, "project", None) or o.get("project"),
                        "status": getattr(o, "status", None) or o.get("status"),
                    }
                    for o in c.get("conflicting_requests", [])
                ],
            }
            for c in conflicts
        ]

        lines = [f"⚠️ Phát hiện {len(conflicts)} đơn mượn đang chờ duyệt bị trùng lịch với đơn khác:\n"]
        for c in conflicts:
            p = c["pending_request"]
            lines.append(f"• **Đơn #{p.id}** ({p.equipment_name} - `{p.equipment_id}` - SL: {p.quantity}) từ {p.needed_from} đến {p.needed_to}:")
            for o in c["conflicting_requests"]:
                lines.append(f"  - Trùng với **Đơn #{o.id}** ({o.requester_name} - Trạng thái: {o.status} - SL: {o.quantity}) từ {o.needed_from} đến {o.needed_to}")
        return "\n".join(lines)

    def _handle_conflict_borrowers(
        self,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_conflict_borrowers"
        conflicts = self.tools.get_schedule_conflicts()
        if not conflicts:
            return "Hiện tại không có xung đột lịch nào được ghi nhận."

        borrowers_map: dict[str, dict[str, Any]] = {}
        for c in conflicts:
            p = c.get("pending_request")
            if p:
                email = getattr(p, "requester_email", None) or p.get("requester_email", "")
                name = getattr(p, "requester_name", None) or p.get("requester_name", "")
                project = getattr(p, "project", None) or p.get("project", "")
                key = email or name
                if key:
                    if key not in borrowers_map:
                        borrowers_map[key] = {
                            "name": name,
                            "email": email,
                            "projects": {project} if project else set(),
                            "role_in_conflict": "Đang yêu cầu mượn (Pending)",
                        }
                    elif project:
                        borrowers_map[key]["projects"].add(project)

            for o in c.get("conflicting_requests", []):
                email = getattr(o, "requester_email", None) or o.get("requester_email", "")
                name = getattr(o, "requester_name", None) or o.get("requester_name", "")
                project = getattr(o, "project", None) or o.get("project", "")
                status = getattr(o, "status", None) or o.get("status", "")
                key = email or name
                if key:
                    if key not in borrowers_map:
                        borrowers_map[key] = {
                            "name": name,
                            "email": email,
                            "projects": {project} if project else set(),
                            "role_in_conflict": f"Đang giữ/đã duyệt ({status})",
                        }
                    else:
                        if project:
                            borrowers_map[key]["projects"].add(project)
                        borrowers_map[key]["role_in_conflict"] += f", {status}"

        trace.tool_result_count = len(borrowers_map)
        lines = [f"Danh sách các nhân sự liên quan đến các xung đột lịch (**{len(borrowers_map)}** người):\n"]
        for b in borrowers_map.values():
            proj_str = f" — Dự án: {', '.join(b['projects'])}" if b["projects"] else ""
            email_str = f" (`{b['email']}`)" if b["email"] else ""
            lines.append(f"- **{b['name']}**{email_str}{proj_str} ({b['role_in_conflict']})")
        return "\n".join(lines)

    def _handle_cancel_action(
        self,
        state: ConversationState,
        trace: AgentTrace,
    ) -> tuple[str, Optional[dict[str, Any]]]:
        state.pending_form = None
        state.pending_action = None
        trace.response_mode = "cancelled"
        return ("Đã hủy thao tác hiện tại. Bạn có thể tra cứu thiết bị hoặc thực hiện yêu cầu mới.", None)

    def _handle_request_detail(
        self,
        plan: QueryPlan,
        state: ConversationState,
        user: SessionData,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_request_detail"
        req_id = plan.target_request_id or _extract_int_req_id(state.active_request)
        if not req_id and state.active_request_ids:
            req_id = state.active_request_ids[0]

        lower_msg = plan.raw_message.lower()

        # Handle chronological previous request ("Còn request trước đó thì sao?", "đơn trước đó")
        if any(p in lower_msg for p in ["trước đó", "trước đấy", "liền trước"]):
            current_active_id = req_id or _extract_int_req_id(state.active_request) or (state.active_request_ids[0] if state.active_request_ids else None)
            all_recent = self.tools.get_recent_requests(limit=10)
            prev_req = None
            if current_active_id:
                for idx, r in enumerate(all_recent):
                    if r.id == current_active_id and idx + 1 < len(all_recent):
                        prev_req = all_recent[idx + 1]
                        break
            if not prev_req and len(all_recent) > 1:
                prev_req = all_recent[1]
            if prev_req:
                req = prev_req
                req_id = prev_req.id
                state.active_request = _to_dict(req)
                state.active_request_ids = [req.id]
                return (
                    f"Yêu cầu trước đó (Đơn #{req.id}) là:\n\n"
                    f"• **Người gửi:** {req.requester_name} ({req.requester_email or 'không rõ email'})\n"
                    f"• **Thiết bị:** {req.equipment_name} (`{req.equipment_id}`)\n"
                    f"• **Dự án:** {req.project}\n"
                    f"• **Số lượng:** {req.quantity} cái\n"
                    f"• **Ngày mượn:** {req.needed_from}\n"
                    f"• **Ngày trả:** {req.needed_to}\n"
                    f"• **Trạng thái:** **{req.status}**"
                )

        if not req_id:
            return "Bạn muốn xem thông tin chi tiết của đơn mượn nào? Vui lòng cho biết mã đơn (ví dụ: `đơn #1`)."

        req = self.tools.get_request_detail(req_id)
        if not req:
            return f"Không tìm thấy đơn mượn #{req_id} trong hệ thống."

        state.active_request = _to_dict(req)
        state.active_request_ids = [req.id]

        # Check if asked about AI priority
        lower_msg = plan.raw_message.lower()
        if any(p in lower_msg for p in ["mức ưu tiên", "priority", "độ ưu tiên", "ưu tiên"]):
            return (
                f"Đối với **Đơn #{req.id}** (`{req.equipment_name}`), AI đề xuất mức ưu tiên: **{req.priority_level}**.\n"
                f"- **Lý do AI:** {req.priority_reason}\n"
                f"- **Dự án:** {req.project} (Người mượn: {req.requester_name})"
            )

        # Check if asked "là của ai"
        if any(w in lower_msg for w in ["của ai", "là ai", "ai tạo", "ai gửi"]):
            return (
                f"Đơn #{req.id} được tạo bởi **{req.requester_name}** (`{req.requester_email or 'không rõ email'}`) "
                f"cho dự án **{req.project}**."
            )

        # Check if asked "project nào" / "dự án nào"
        if any(w in lower_msg for w in ["project nào", "dự án nào"]):
            return (
                f"Đơn #{req.id} (`{req.equipment_name}`) được tạo cho dự án **{req.project}** bởi **{req.requester_name}**."
            )

        # Check if asked "mượn gì" / "mượn thiết bị gì"
        if any(w in lower_msg for w in ["mượn gì", "mượn thiết bị gì", "thiết bị gì"]):
            return (
                f"Đơn #{req.id} đăng ký mượn thiết bị **{req.equipment_name}** (`{req.equipment_id}`) với số lượng **{req.quantity} cái** cho dự án **{req.project}**."
            )

        return (
            f"**Chi tiết đơn mượn #{req.id}**:\n"
            f"- **Người mượn:** {req.requester_name} ({req.requester_email})\n"
            f"- **Dự án:** {req.project}\n"
            f"- **Thiết bị:** `{req.equipment_id}` - {req.equipment_name}\n"
            f"- **Số lượng:** {req.quantity}\n"
            f"- **Thời gian:** {req.needed_from} đến {req.needed_to}\n"
            f"- **Mục đích:** {req.purpose}\n"
            f"- **Độ ưu tiên AI đề xuất:** {req.priority_level}\n"
            f"- **Lý do AI:** {req.priority_reason}\n"
            f"- **Mức ưu tiên quản lý chốt:** {req.final_priority_level or 'Chưa đánh giá'}\n"
            f"- **Trạng thái hiện tại:** **{req.status}**"
        )

    def _handle_priority_review(
        self,
        plan: QueryPlan,
        state: ConversationState,
        user: SessionData,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "review_priority"
        if not user.is_manager and not user.is_admin:
            return "Chỉ quản lý (Manager) mới có quyền đánh giá và điều chỉnh mức ưu tiên của yêu cầu."

        req_id = plan.target_request_id or _extract_int_req_id(state.active_request) or (state.active_request_ids[0] if state.active_request_ids else None)
        if not req_id:
            return "Bạn muốn điều chỉnh độ ưu tiên cho đơn nào? Vui lòng cung cấp mã đơn (ví dụ: `đơn #1`)."

        if not plan.new_priority:
            return "Bạn muốn đổi mức ưu tiên của đơn thành mức nào? (Cho phép: Critical, High, Medium, Low, Needs review)"

        new_prio = plan.new_priority
        updated = self.tools.review_priority(
            request_id=req_id,
            new_priority=new_prio,
            reviewer_name=user.user_name,
            reviewer_email=user.user_email,
        )
        state.active_request = _to_dict(updated)
        return f"Đã cập nhật mức ưu tiên của **Đơn #{req_id}** thành **{new_prio}** thành công."

    def _handle_approve_request(
        self,
        plan: QueryPlan,
        state: ConversationState,
        user: SessionData,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "approve_request"
        if not user.is_manager and not user.is_admin:
            return "Chỉ quản lý (Manager) mới có quyền phê duyệt yêu cầu mượn thiết bị."

        req_id = plan.target_request_id or _extract_int_req_id(state.active_request) or (state.active_request_ids[0] if state.active_request_ids else None)
        if not req_id:
            return "Bạn muốn phê duyệt đơn nào? Vui lòng cung cấp mã đơn (ví dụ: `duyệt đơn #1`)."

        req = self.tools.get_request_detail(req_id)
        if not req:
            return f"Không tìm thấy đơn mượn #{req_id} trong hệ thống."

        # Self-approval guard
        if (req.requester_email or "").strip().lower() == user.user_email.strip().lower():
            return "❌ Không thể phê duyệt: Quản lý không thể tự phê duyệt yêu cầu mượn của chính mình."

        try:
            approved = self.tools.approve_request(
                request_id=req_id,
                manager_email=user.user_email,
                manager_name=user.user_name,
            )
            state.active_request = _to_dict(approved)
            return f"✅ Đã phê duyệt **Đơn #{req_id}** cho `{approved.equipment_name}` thành công!"
        except PermissionError as p_err:
            return f"❌ Không thể phê duyệt: {str(p_err)}"
        except Exception as ex:
            return f"❌ Lỗi khi phê duyệt đơn #{req_id}: {str(ex)}"

    def _handle_reject_request(
        self,
        plan: QueryPlan,
        state: ConversationState,
        user: SessionData,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "reject_request"
        if not user.is_manager and not user.is_admin:
            return "Chỉ quản lý (Manager) mới có quyền từ chối yêu cầu mượn thiết bị."

        req_id = plan.target_request_id or _extract_int_req_id(state.active_request) or (state.active_request_ids[0] if state.active_request_ids else None)
        if not req_id:
            return "Bạn muốn từ chối đơn nào? Vui lòng cung cấp mã đơn (ví dụ: `từ chối đơn #1`)."

        req = self.tools.get_request_detail(req_id)
        if not req:
            return f"Không tìm thấy đơn mượn #{req_id} trong hệ thống."

        # Self-rejection guard
        if (req.requester_email or "").strip().lower() == user.user_email.strip().lower():
            return "❌ Không thể từ chối: Quản lý không thể tự xử lý yêu cầu mượn của chính mình."

        reason = plan.reject_reason or "Không đáp ứng điều kiện"
        try:
            rejected = self.tools.reject_request(
                request_id=req_id,
                manager_name=user.user_name,
                manager_email=user.user_email,
                reason=reason,
            )
            state.active_request = _to_dict(rejected)
            return f"Đã từ chối **Đơn #{req_id}** với lý do: {reason}."
        except PermissionError as p_err:
            return f"❌ Không thể từ chối: {str(p_err)}"
        except Exception as ex:
            return f"❌ Lỗi khi từ chối đơn #{req_id}: {str(ex)}"

    # -------------------------------------------------------------
    # Admin Handlers
    # -------------------------------------------------------------

    def _handle_add_user(
        self,
        plan: QueryPlan,
        user: SessionData,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "add_user_account"
        if not user.is_admin:
            return "Chỉ quản trị viên (Admin) mới có quyền tạo tài khoản người dùng mới."

        msg = plan.raw_message
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", msg)
        if not email_match:
            return "Vui lòng cung cấp email hợp lệ của người dùng cần tạo (ví dụ: `nguyena@bosch.com`)."

        target_email = email_match.group(0)
        target_role = "USER"
        if re.search(r"\b(manager|quản lý)\b", msg, re.IGNORECASE):
            target_role = "MANAGER"

        name_match = re.search(r"(?:tên|name)\s+([A-Za-zÀ-ỹ\s]+?)(?=\s+(?:role|vai trò|email|$))", msg, re.IGNORECASE)
        target_name = name_match.group(1).strip() if name_match else target_email.split("@")[0].title()

        try:
            res = self.tools.add_user_account(
                user_email=target_email,
                user_name=target_name,
                role=target_role,
                actor_role=user.role,
            )
            return (
                f"✅ Đã tạo tài khoản thành công cho **{res['user_name']}**:\n"
                f"- Email: `{res['user_email']}`\n"
                f"- Vai trò: **{res['role']}**\n"
                f"- Trạng thái: Hoạt động"
            )
        except Exception as ex:
            return f"❌ Không thể tạo tài khoản: {str(ex)}"

    def _handle_user_management(self, user: SessionData, trace: AgentTrace) -> str:
        trace.selected_tool = "list_users"
        if not user.is_admin:
            return "Chỉ quản trị viên (Admin) mới có quyền quản lý người dùng và phân quyền."

        users = self.tools.list_users()
        lines = [f"Danh sách người dùng hệ thống (**{len(users)}** người dùng):\n"]
        for u in users:
            status = "Hoạt động" if u.is_active else "Đã vô hiệu hóa"
            lines.append(f"- **{u.user_name}** (`{u.user_email}`): Role **{u.role}** ({status})")
        return "\n".join(lines)

    def _handle_help(self, user: SessionData) -> str:
        is_mgr = user.is_manager or user.is_admin
        is_adm = user.is_admin

        lines = [
            "**Hướng dẫn sử dụng Trợ lý AI Quản lý Kho:**\n",
            "1. **Tra cứu thiết bị kỹ thuật:**",
            "   - Tìm kiếm: `Cho mình xem danh sách connector góc vuông 4.2mm ở Tủ 1`",
            "   - Kiểm tra số lượng: `TU1-001 còn bao nhiêu cái?`",
            "   - Vị trí thiết bị: `EBS-030 ở đâu?`\n",
            "2. **Hỗ trợ tạo đơn mượn:**",
            "   - `Mình muốn mượn TU1-001`",
            "   - `5 cái từ 10/10 đến 12/10 để test board cho project ABC`\n",
        ]
        if is_mgr:
            lines.extend([
                "3. **Tính năng Quản lý (Manager):**",
                "   - `Có bao nhiêu đơn đang chờ duyệt?`",
                "   - `Danh sách đơn pending`",
                "   - `Đơn thứ 2 là của ai?`",
                "   - `AI đề xuất mức ưu tiên gì cho đơn này?`",
                "   - `Tôi đổi priority thành High`",
                "   - `Duyệt đơn 1` hoặc `Từ chối đơn 1 vì thiếu thông tin`\n",
            ])
        if is_adm:
            lines.append("4. **Tính năng Quản trị (Admin):**\n   - `Danh sách user` để xem tài khoản và quyền.")

        return "\n".join(lines)

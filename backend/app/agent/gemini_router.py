"""Dedicated Structured LLM Router for AI Equipment Agent.

Uses google-genai SDK with structured output validation, compact context,
and automatic fallback to legacy QueryRouter.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.agent.models import (
    ConversationState,
    GeminiRouterOutput,
    IntentType,
    QueryPlan,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

_ROUTER_SYSTEM_INSTRUCTION = """You are the semantic intent, entity, and reference classifier for a technical equipment management system.
Analyze the user message and compact conversation context, then return a valid JSON object.

Allowed intents (choose exactly one matching the user's primary goal):
- equipment_detail: user asks for specifications, location, details of a specific equipment.
- equipment_count: user asks how many units are available or remaining of an equipment.
- equipment_exists: user asks if the warehouse has an equipment or checks inventory existence.
- equipment_search: user searches or lists equipment based on attributes (connector, board, sensor, size, pins, category, location).
- quantity_sufficiency: user asks if an equipment has enough for a requested quantity (e.g. "có đủ 50 cái không?").
- alternative_search: user asks for replacement, substitute, similar alternative equipment (e.g. "loại nào tương tự", "thiết bị thay thế", "hết rồi có loại nào khác").
- external_sourcing: user explicitly asks where to buy/purchase, external shops, pricing options outside the warehouse (e.g. "tìm nơi bán", "mua ở đâu", "shop nào có").
- request_create: user wants to borrow equipment or initiate a borrow request.
- return_request: user wants to return borrowed equipment.
- my_requests: user asks to view/check the status of their own borrow requests.
- active_loans: user/manager asks for all currently borrowed items.
- active_borrowers: user/manager asks for the list or identities of people currently borrowing.
- active_borrowers_count: user asks how many people are currently borrowing equipment.
- pending_request_count: manager asks how many requests need review/approval.
- pending_request_list: manager asks to view requests awaiting approval.
- recent_request: user/manager asks who made the latest request or what the most recent request is.
- overdue_loans: user/manager asks who is overdue, returning late, or what loans are past due.
- overdue_borrowers: user/manager asks for the identities of overdue borrowers.
- schedule_conflicts: user/manager asks about scheduling conflicts between requests.
- conflict_borrowers: user/manager asks which people/users are affected by schedule conflicts.
- usage_query: user asks which project is currently using an equipment.
- schedule_planning: user asks when an equipment will be released or available for another project.
- list_users: admin asks to view system users.
- add_user: admin asks to add/create a new user or manager.
- cancel_action: user explicitly cancels or abandons a pending borrow/return action (e.g. "mình muốn xem thôi", "không mượn nữa", "hủy thao tác").
- help: general assistance inquiry.
- unknown: message cannot be classified into any domain.

CRITICAL RULES FOR EXTRACTION:
1. Equipment vs Project Separation:
   - "Mình cần CANInterface XYZ cho project Alpha" -> equipment_name = "CANInterface XYZ", project = "Alpha". NEVER put project into equipment keywords.
2. Negation & Cancellation Handling:
   - "Không cần mượn, chỉ cho mình biết..." -> NOT request_create. is_negation_or_cancellation = true.
   - "Mình muốn xem thôi" after a return prompt -> intent = cancel_action, is_negation_or_cancellation = true.
3. Alternative Equipment Search:
   - If user asks for replacement for X (e.g. "loại nào tương tự TU1-001"), intent = "alternative_search", equipment_id/name = target to replace.
4. External Sourcing:
   - Only set when user explicitly asks to BUY, PURCHASE, or find SHOPS/SELLERS externally.
5. Reference Types:
   - "nó", "thiết bị này" -> reference.type = "active_equipment", reference.is_pronoun = true.
   - "cái thứ 2", "món thứ 1" -> reference.ordinal_index = 2 (or 1), reference.type = "previous_result".
   - "những người đó là ai" -> reference.is_group_reference = true, reference.type = "group_people".
   - "những người nào bị xung đột" -> reference.is_group_reference = true, reference.type = "group_people".

Return JSON matching this exact structure:
{
  "intent": string,
  "confidence": float,
  "equipment": {
    "equipment_id": string | null,
    "equipment_name": string | null
  },
  "request": {
    "quantity": integer | null,
    "project": string | null,
    "purpose": string | null,
    "needed_from": string | null,
    "needed_to": string | null
  },
  "constraints": {
    "category": string | null,
    "geometry": string | null,
    "size_mm": float | null,
    "pins": integer | null,
    "location": string | null,
    "color": string | null,
    "gender": string | null,
    "keywords": [string]
  },
  "reference": {
    "type": string,
    "ordinal_index": integer | null,
    "is_pronoun": boolean,
    "is_group_reference": boolean
  },
  "external_search_requested": boolean,
  "is_negation_or_cancellation": boolean,
  "clarification_needed": boolean,
  "clarification_reason": string | null,
  "reasoning": string | null
}
"""

FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
]


class GeminiAgentRouter:
    """Structured LLM classifier converting natural language into typed GeminiRouterOutput."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.1-flash-lite",
        model: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._model_name = model or model_name or "gemini-3.1-flash-lite"

    def classify_message(
        self,
        raw_message: str,
        user_role: Any = "USER",
        state: Optional[ConversationState] = None,
        recent_history: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[GeminiRouterOutput]:
        """Classify message with structured JSON output. Returns None on any failure."""
        if isinstance(user_role, ConversationState):
            actual_state = user_role
            actual_role = str(state) if isinstance(state, str) else "USER"
            state = actual_state
            user_role = actual_role
        elif not isinstance(user_role, str):
            user_role = "USER"

        if not self._api_key or not self._api_key.strip():
            logger.debug("Gemini API key is not configured; skipping LLM router.")
            return None

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            logger.warning("google-genai SDK not installed; skipping LLM router.")
            return None

        # Build compact context without leaking inventory details (privacy guard)
        context_parts = [f"User Role: {user_role.upper()}"]
        if state:
            if state.active_equipment:
                eq_id = state.active_equipment.get("EquipmentID") or state.active_equipment.get("equipment_id")
                eq_name = state.active_equipment.get("EquipmentName") or state.active_equipment.get("equipment_name")
                context_parts.append(f"Active Equipment Context: ID={eq_id}, Name={eq_name}")
            if state.active_request:
                req_id = state.active_request.get("id") or state.active_request.get("RequestID")
                context_parts.append(f"Active Request Context: ID={req_id}")
            if state.last_intent:
                context_parts.append(f"Previous Intent: {state.last_intent.value}")
            if state.last_result_type:
                context_parts.append(f"Previous Result Type: {state.last_result_type}")
                context_parts.append(f"Previous Result Count: {state.last_result_count}")
                # Provide brief IDs of previous result items (up to 5) for ordinal/group references
                if state.last_result_set:
                    brief_items = []
                    for idx, item in enumerate(state.last_result_set[:5], start=1):
                        it_id = item.get("EquipmentID") or item.get("equipment_id") or item.get("id") or item.get("RequestID") or item.get("name")
                        it_name = item.get("EquipmentName") or item.get("equipment_name") or item.get("borrower") or ""
                        brief_items.append(f"#{idx}: {it_id} ({it_name})")
                    context_parts.append(f"Previous Result Items: [{', '.join(brief_items)}]")
            if state.pending_action:
                context_parts.append(f"Pending Action: {state.pending_action}")

        # Add recent conversation turns (max 3 turns)
        if recent_history:
            history_lines = []
            for h in recent_history[-3:]:
                role = h.get("role", "user")
                content = str(h.get("content", ""))[:120]
                history_lines.append(f"{role}: {content}")
            if history_lines:
                context_parts.append("Recent conversation:\n" + "\n".join(history_lines))

        full_prompt = f"Context:\n" + "\n".join(context_parts) + f"\n\nUser Message: {raw_message}"

        config = types.GenerateContentConfig(
            system_instruction=_ROUTER_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.0,
        )

        models_to_try = [self._model_name]
        for m in FALLBACK_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        client = genai.Client(api_key=self._api_key)

        for attempt_idx, model in enumerate(models_to_try):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=full_prompt,
                    config=config,
                )
                raw_text = response.text.strip()
                parsed = json.loads(raw_text)
                validated = GeminiRouterOutput.model_validate(parsed)
                return validated
            except Exception as e:
                logger.warning("Gemini router attempt %d on model %s failed: %s", attempt_idx + 1, model, e)
                continue

        logger.error("All candidate models for Gemini router failed; falling back.")
        return None

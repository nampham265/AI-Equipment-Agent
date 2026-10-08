"""Thread-safe conversation state manager for Agent Orchestration."""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from app.agent.models import ConversationState, PendingForm, IntentType


def _extract_request_num(item: dict[str, Any]) -> int:
    val = item.get("id")
    if isinstance(val, int) and val > 0:
        return val
    req_val = item.get("RequestID") or item.get("request_id") or val
    if req_val:
        if isinstance(req_val, int):
            return req_val
        m = re.search(r"(\d+)", str(req_val))
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return 0


class ConversationStateManager:
    """In-memory thread-safe state store indexed by (user_email, conversation_id)."""

    def __init__(self) -> None:
        self._states: dict[tuple[str, str], ConversationState] = {}
        self._lock = threading.Lock()

    def _make_key(self, user_email: str, conversation_id: str) -> tuple[str, str]:
        return (user_email.strip().lower(), conversation_id.strip())

    def get_state(self, user_email: str, conversation_id: str) -> ConversationState:
        key = self._make_key(user_email, conversation_id)
        with self._lock:
            if key not in self._states:
                self._states[key] = ConversationState(
                    conversation_id=conversation_id.strip(),
                    user_email=user_email.strip().lower(),
                )
            return self._states[key].model_copy(deep=True)

    def save_state(self, state: ConversationState) -> None:
        key = self._make_key(state.user_email, state.conversation_id)
        state.updated_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._states[key] = state.model_copy(deep=True)

    def clear_state(self, user_email: str, conversation_id: str) -> None:
        key = self._make_key(user_email, conversation_id)
        with self._lock:
            self._states.pop(key, None)

    def set_result_set(
        self,
        state: ConversationState,
        results: list[dict[str, Any]],
        result_type: str = "equipment",
        page: int = 1,
        page_size: int = 10,
        result_schema: Optional[str] = None,
    ) -> None:
        """Store search/query results for pagination and ordinal referencing."""
        state.last_result_set = results
        state.last_result_type = result_type
        state.last_result_count = len(results)
        state.result_schema = result_schema or result_type
        state.last_result_page = page
        state.last_page_size = page_size
        if results:
            state.last_selected_item = results[0]
        else:
            state.last_selected_item = None

        if result_type == "equipment":
            state.active_equipment_ids = [
                str(r.get("EquipmentID") or r.get("equipment_id") or "")
                for r in results
                if (r.get("EquipmentID") or r.get("equipment_id"))
            ]
            if results:
                state.active_equipment = results[0]
        elif result_type in ["request", "overdue_loans", "active_loans", "user_requests", "borrowed_loans", "active_borrowers"]:

            state.active_request_ids = [
                _extract_request_num(r)
                for r in results
                if _extract_request_num(r) > 0
            ]
            if results:
                state.active_request = results[0]

    def get_item_by_ordinal(
        self,
        state: ConversationState,
        ordinal_1_based: int,
    ) -> Optional[dict[str, Any]]:
        """Resolve 'cái thứ 2', 'đơn thứ 1' against the stored result set.
        
        Note: We support both page-relative (if ordinal is within page size)
        and global index (0-based: index = ordinal - 1).
        By default, in user conversational context, 'cái thứ 2' refers to the 2nd
        item currently displayed or in the current result set.
        """
        if not state.last_result_set or ordinal_1_based < 1:
            return None
        
        idx = ordinal_1_based - 1
        if 0 <= idx < len(state.last_result_set):
            item = state.last_result_set[idx]
            state.last_selected_item = item
            if state.last_result_type == "equipment":
                state.active_equipment = item
                eq_id = str(item.get("EquipmentID") or item.get("equipment_id") or "")
                if eq_id and eq_id not in state.active_equipment_ids:
                    state.active_equipment_ids.insert(0, eq_id)
            elif state.last_result_type in ["request", "overdue_loans", "active_loans", "user_requests"]:
                state.active_request = item
                req_id = _extract_request_num(item)
                if req_id and req_id not in state.active_request_ids:
                    state.active_request_ids.insert(0, req_id)
                eq_id = str(item.get("EquipmentID") or item.get("equipment_id") or "")
                if eq_id:
                    state.active_equipment = item
                    if eq_id not in state.active_equipment_ids:
                        state.active_equipment_ids.insert(0, eq_id)
            return item
        return None

    def get_page_items(
        self,
        state: ConversationState,
        page: int,
    ) -> tuple[list[dict[str, Any]], int, int, int]:
        """Returns: (items_in_page, current_page, total_pages, remaining_count)"""
        if not state.last_result_set:
            return ([], 1, 0, 0)
        
        page_size = max(1, state.last_page_size)
        total_items = len(state.last_result_set)
        total_pages = (total_items + page_size - 1) // page_size
        
        current_page = max(1, min(page, total_pages))
        start_idx = (current_page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)
        
        page_items = state.last_result_set[start_idx:end_idx]
        remaining = max(0, total_items - end_idx)
        
        state.last_result_page = current_page
        return (page_items, current_page, total_pages, remaining)


# Singleton instance
state_manager = ConversationStateManager()

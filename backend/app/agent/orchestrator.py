"""End-to-end Agent Orchestrator: Context, Planning, Deterministic Tools & Response."""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.agent.models import (
    AgentTrace,
    ConversationState,
    IntentType,
    PendingForm,
    QueryPlan,
)
from app.agent.normalizer import (
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


class AgentOrchestrator:
    """Central orchestrator executing the 8-step Agent pipeline."""

    def __init__(self, tools: AgentTools) -> None:
        self.tools = tools

    def process_message(
        self,
        raw_message: str,
        user: SessionData,
        conversation_id: str,
    ) -> dict[str, Any]:
        """Main entrypoint for agent conversations."""
        # 1. State lookup
        state = state_manager.get_state(user.user_email, conversation_id)

        # 2. Routing & Intent / Entity / Context resolution
        plan = query_router.route_message(raw_message, state)

        # 3. Create Trace object
        trace = AgentTrace(
            conversation_id=conversation_id,
            user_role=user.role.upper(),
            intent=plan.intent.value,
            intent_confidence=plan.intent_confidence,
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

            elif plan.intent == IntentType.SCHEDULE_PLANNING_QUERY:
                response_text = self._handle_schedule_planning(plan, state, trace)

            elif plan.intent == IntentType.EQUIPMENT_CONDITION_QUERY:
                response_text = self._handle_condition_query(plan, state, trace)

            elif plan.intent == IntentType.REQUEST_CREATE:
                response_text, action_payload = self._handle_request_create(plan, state, user, trace)

            elif plan.intent == IntentType.MY_REQUESTS:
                response_text = self._handle_my_requests(plan, user, state, trace)

            elif plan.intent == IntentType.RETURN_REQUEST:
                response_text, action_payload = self._handle_return_request(plan, user, state, trace)

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
                response_text = self._handle_active_loans(state, trace)

            elif plan.intent == IntentType.ACTIVE_LOANS_COUNT:
                response_text = self._handle_active_loans_count(state, trace)

            elif plan.intent == IntentType.ACTIVE_BORROWERS:
                response_text = self._handle_active_borrowers(state, trace)

            elif plan.intent == IntentType.ACTIVE_BORROWERS_COUNT:
                response_text = self._handle_active_borrowers_count(state, trace)

            elif plan.intent == IntentType.SCHEDULE_CONFLICTS:
                response_text = self._handle_schedule_conflicts(state, trace)

            elif plan.intent == IntentType.REQUEST_DETAIL:
                response_text = self._handle_request_detail(plan, state, user, trace)

            elif plan.intent == IntentType.PRIORITY_REVIEW:
                response_text = self._handle_priority_review(plan, state, user, trace)

            elif plan.intent == IntentType.APPROVE_REQUEST:
                response_text = self._handle_approve_request(plan, state, user, trace)

            elif plan.intent == IntentType.REJECT_REQUEST:
                response_text = self._handle_reject_request(plan, state, user, trace)

            # Admin intents
            elif plan.intent == IntentType.USER_MANAGEMENT:
                response_text = self._handle_user_management(user, trace)

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

    def _handle_equipment_count(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_equipment_count"
        eq_id = plan.entity_id

        # If user provided search keywords/constraints, search first instead of falling back to stale context
        has_new_subject = bool(plan.constraints.keywords or plan.constraints.category or plan.constraints.location or plan.constraints.geometry or plan.constraints.color)
        if not eq_id and has_new_subject:
            matched = self.tools.search_equipment(plan.constraints, query=plan.raw_message)
            if len(matched) == 1:
                eq_id = matched[0].equipment_id
            elif len(matched) > 1:
                serialized_results = [_to_dict(r) for r in matched]
                state_manager.set_result_set(state, serialized_results, result_type="equipment", page=1, page_size=15)
                options = "\n".join([f"• `{it.get('equipment_id')}`: **{it.get('equipment_name')}**" for it in serialized_results])
                return (
                    f"Tôi tìm thấy nhiều thiết bị phù hợp với câu hỏi của bạn:\n\n{options}\n\n"
                    f"Vui lòng cung cấp mã hoặc tên chính xác hơn để kiểm tra số lượng."
                )

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
        return f"{explanation}\n- **Vị trí lưu trữ:** {info['location']}"

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
            return "Bạn muốn kiểm tra tính khả dụng của thiết bị nào?"

        needed_from = plan.needed_from or "2026-01-01"
        needed_to = plan.needed_to or "2026-12-31"

        avail = self.tools.check_availability(eq_id, needed_from, needed_to)
        return (
            f"Tính khả dụng của thiết bị `{eq_id}` (từ {needed_from} đến {needed_to}):\n"
            f"- Tổng số lượng: {avail['quantity_total']}\n"
            f"- Số lượng đã cam kết: {avail['committed_quantity']}\n"
            f"- Số lượng khả dụng: **{avail['available_quantity']}**\n"
            f"- Đơn trùng lịch chờ duyệt: {len(avail.get('competing_pending_requests', []))}"
        )

    def _handle_project_usage(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        trace.selected_tool = "get_equipment_active_loans"
        eq_id = plan.entity_id or (state.active_equipment.get("EquipmentID") if state.active_equipment else None)
        if not eq_id:
            return "Bạn muốn kiểm tra dự án sử dụng cho thiết bị nào?"

        loans = self.tools.get_equipment_active_loans(eq_id)
        if not loans:
            return (
                f"Hiện hệ thống chưa có dữ liệu đáng tin cậy về project đang sử dụng `{eq_id}`.\n"
                f"*(Lưu ý: Hệ thống quản lý kho hiện tại chỉ theo dõi qua các đơn mượn đã phê duyệt, "
                f"chưa hỗ trợ định vị thiết bị thời gian thực theo từng dự án)*"
            )

        lines = [f"Các đơn mượn đang sử dụng thiết bị `{eq_id}`:\n"]
        for r in loans:
            lines.append(f"- Dự án **{r.project}** (Người mượn: {r.requester_name}, Số lượng: {r.quantity}, từ {r.needed_from} đến {r.needed_to})")
        return "\n".join(lines)

    def _handle_usage_query(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
        eq_id = plan.entity_id or (state.active_equipment.get("EquipmentID") if state.active_equipment else None)
        if not eq_id:
            return "Bạn muốn hỏi thời gian nhận lại/trả của thiết bị nào?"

        loans = self.tools.get_equipment_active_loans(eq_id)
        if not loans:
            return f"Thiết bị `{eq_id}` hiện không có đơn mượn nào đang diễn ra, hoặc hệ thống chưa có đủ dữ liệu lịch trình để xác định thời gian."

        lines = [f"Lịch hoàn trả dự kiến cho thiết bị `{eq_id}`:\n"]
        for r in loans:
            lines.append(f"- Đơn #{r.id} (Dự án {r.project}): Dự kiến hoàn trả vào ngày **{r.needed_to}**")
        return "\n".join(lines)

    def _handle_schedule_planning(
        self,
        plan: QueryPlan,
        state: ConversationState,
        trace: AgentTrace,
    ) -> str:
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
        eq_id = plan.entity_id or (state.pending_form.equipment_id if state.pending_form else None)
        if not eq_id and state.active_equipment:
            eq_id = state.active_equipment.get("EquipmentID")
        if not eq_id and state.active_equipment_ids:
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

        eq = self.tools.get_equipment_detail(eq_id)
        eq_name = eq.equipment_name if eq else (state.active_equipment.get("EquipmentName") if state.active_equipment else eq_id)

        # Merge or create pending form
        if not state.pending_form:
            state.pending_form = PendingForm(
                equipment_id=eq_id,
                equipment_name=eq_name,
            )
        else:
            state.pending_form.equipment_id = eq_id
            state.pending_form.equipment_name = eq_name

        if plan.quantity:
            state.pending_form.quantity = plan.quantity
        if plan.needed_from:
            state.pending_form.needed_from = plan.needed_from
        if plan.needed_to:
            state.pending_form.needed_to = plan.needed_to
        if plan.project:
            state.pending_form.project = plan.project
        if plan.purpose:
            state.pending_form.purpose = plan.purpose

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
        trace.tool_arguments = {"user_email": user.user_email, "status": plan.status_filter}
        requests = self.tools.list_my_requests(user.user_email, status=plan.status_filter)
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
                return "Bạn không có yêu cầu mượn nào ở trạng thái Đã duyệt (Approved)."
            elif plan.status_filter == "Pending":
                return "Bạn không có yêu cầu mượn nào đang chờ duyệt (Pending)."
            elif plan.status_filter == "Borrowed":
                return "Hiện tại bạn không có thiết bị nào đang trong trạng thái mượn (Borrowed)."
            elif plan.status_filter == "Rejected":
                return "Bạn không có yêu cầu mượn nào bị từ chối (Rejected)."
            return "Bạn chưa có yêu cầu mượn thiết bị nào trong hệ thống."

        status_label = ""
        if plan.status_filter == "Approved":
            status_label = " đã được duyệt"
        elif plan.status_filter == "Pending":
            status_label = " đang chờ duyệt"
        elif plan.status_filter == "Borrowed":
            status_label = " đang mượn"
        elif plan.status_filter == "Rejected":
            status_label = " bị từ chối"

        lines = [
            f"📋 **Các yêu cầu mượn thiết bị{status_label} của bạn** ({len(requests)} yêu cầu):\n",
            "| Mã YC | Thiết bị | Dự án | SL | Ngày mượn | Ngày trả | Mức ưu tiên | Trạng thái |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in requests[:10]:
            req_id_str = getattr(r, "request_id", None) or getattr(r, "display_id", None) or f"REQ-{r.id:06d}"
            eq_name = r.equipment_name or r.equipment_id
            eq_display = f"`{r.equipment_id}` ({eq_name})" if r.equipment_name else f"`{r.equipment_id}`"
            prio = r.final_priority_level or r.priority_level or "Needs review"
            n_from = (r.needed_from or "")[:10]
            n_to = (r.needed_to or "")[:10]
            lines.append(
                f"| {req_id_str} | {eq_display} | {r.project} | {r.quantity} | {n_from} | {n_to} | {prio} | {r.status} |"
            )
        return "\n".join(lines)

    # -------------------------------------------------------------
    # Manager Handlers
    # -------------------------------------------------------------

    def _handle_pending_request_count(self, user: SessionData, trace: AgentTrace) -> str:
        trace.selected_tool = "count_pending_requests"
        if not user.is_manager and not user.is_admin:
            return "Chỉ quản lý (Manager) mới có quyền kiểm tra số lượng đơn chờ duyệt."

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
            return "Chỉ quản lý (Manager) mới có quyền xem danh sách đơn chờ duyệt."

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

        if not loans:
            return "Hiện tại không có thiết bị nào đang trong trạng thái được mượn (Borrowed)."

        lines = [
            f"📦 Danh sách **{len(loans)}** thiết bị đang được mượn:\n",
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

        # Ordinal resolution: "Tôi muốn trả cái thứ 2" against last borrowed_loans result set
        target_loan = None
        if plan.ordinal_index is not None and state.last_result_type == "borrowed_loans" and state.last_result_set:
            item = state_manager.get_item_by_ordinal(state, plan.ordinal_index)
            if item:
                req_id = item.get("id") or item.get("request_id")
                if req_id:
                    matched = [r for r in active_loans if r.id == req_id]
                    if matched:
                        target_loan = matched[0]

        # Equipment ID / name in message: "Tôi muốn trả TU1-001"
        if not target_loan and plan.entity_id:
            matched = [r for r in active_loans if r.equipment_id.upper() == plan.entity_id.upper()]
            if len(matched) == 1:
                target_loan = matched[0]

        # Exactly one active loan → auto-select
        if not target_loan and len(active_loans) == 1:
            target_loan = active_loans[0]

        # One loan found → open return form
        if target_loan:
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
            action_payload = {
                "type": "show_return_form",
                "prefill": {
                    "request_id": target_loan.id,
                    "display_id": req_id_str,
                    "equipment_id": target_loan.equipment_id,
                    "equipment_name": target_loan.equipment_name,
                    "project": target_loan.project,
                    "quantity": target_loan.quantity,
                    "needed_from": target_loan.needed_from,
                    "needed_to": target_loan.needed_to,
                },
            }
            reply = (
                f"Bạn đang mượn **{target_loan.equipment_name}** (`{target_loan.equipment_id}`) — "
                f"{target_loan.quantity} cái, dự án **{target_loan.project}**.\n\n"
                f"Vui lòng điền thông tin trả bên dưới:"
            )
            return (reply, action_payload)

        # Multiple loans → selection list
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
        conflicts = self.tools.get_schedule_conflicts()
        if not conflicts:
            return "Hiện tại không có đơn mượn nào bị xung đột lịch trùng ngày."

        lines = [f"⚠️ Phát hiện {len(conflicts)} đơn mượn đang chờ duyệt bị trùng lịch với đơn khác:\n"]
        for c in conflicts:
            p = c["pending_request"]
            lines.append(f"• **Đơn #{p.id}** ({p.equipment_name} - `{p.equipment_id}` - SL: {p.quantity}) từ {p.needed_from} đến {p.needed_to}:")
            for o in c["conflicting_requests"]:
                lines.append(f"  - Trùng với **Đơn #{o.id}** ({o.requester_name} - Trạng thái: {o.status} - SL: {o.quantity}) từ {o.needed_from} đến {o.needed_to}")
        return "\n".join(lines)

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

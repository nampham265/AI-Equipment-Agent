"""Intent and constraint extraction router for Agent Orchestration."""
from __future__ import annotations

import re
from typing import Optional

from app.agent.models import (
    ConversationState,
    ExtractedConstraints,
    IntentType,
    QueryPlan,
)
from app.agent.normalizer import (
    check_ask_auto_approve,
    check_existence_query,
    check_negate_borrow,
    check_next_page,
    check_pronoun_reference,
    extract_borrow_fields,
    extract_equipment_id,
    extract_ordinal,
    extract_request_id,
    normalize_equipment_ids,
    normalize_units,
    normalize_whitespace,
)
from app.agent.state import state_manager


# Location regexes
LOCATION_REGEX = re.compile(
    r"\b(Tủ\s*1|Tủ\s*2|Tủ\s*3|Tủ\s*CSW|CSW|EBS_LAB|EBS|LAB)\b",
    re.IGNORECASE,
)

# Geometry regexes: right-angle / góc vuông / R/A, SMD, Through-hole
GEOMETRY_REGEX = re.compile(
    r"\b(R/?A|right[- ]?angle|góc\s*vuông|SMD|thẳng|straight)\b",
    re.IGNORECASE,
)

# Pitch / size regexes: 4.2mm, 3mm, 2.54mm, 4.0mm
SIZE_REGEX = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm|ly)\b",
    re.IGNORECASE,
)

# Pin / pos regexes: 10pos, 10 chân, 6pin, 24 pin
PIN_REGEX = re.compile(
    r"(\d+)\s*(?:pos|pin|chân)\b",
    re.IGNORECASE,
)

# Category regexes: connector, board, sensor, cable, switch
CATEGORY_REGEX = re.compile(
    r"\b(connector|đầu\s*nối|board|mạch|bo\s*mạch|sensor|cảm\s*biến|cable|dây\s*cáp|cáp|switch|công\s*tắc)\b",
    re.IGNORECASE,
)

# Color regexes: đen, trắng, vàng, tím, đỏ, black, white, red
COLOR_REGEX = re.compile(
    r"\b(màu\s*đen|màu\s*trắng|màu\s*vàng|màu\s*tím|màu\s*đỏ|đen|trắng|black|white|yellow|purple|đỏ|red)\b",
    re.IGNORECASE,
)

# Gender regexes: female / cái vs male / đực
GENDER_REGEX = re.compile(
    r"\b(female|ổ\s*cái|loại\s*cái|đầu\s*cái|male|ổ\s*đực|loại\s*đực|đầu\s*đực|lõi\s*đực)\b",
    re.IGNORECASE,
)


def _extract_int_req_id(d: Optional[dict]) -> Optional[int]:
    """Safely extract integer request id from dict."""
    if not d:
        return None
    val = d.get("id")
    if isinstance(val, int) and val > 0:
        return val
    req_str = str(d.get("RequestID") or d.get("request_id") or val or "")
    if "-" in req_str:
        try:
            return int(req_str.split("-")[-1])
        except (ValueError, IndexError):
            pass
    extracted = extract_request_id(req_str)
    if extracted is not None:
        return extracted
    m = re.findall(r"\d+", req_str)
    return int(m[-1]) if m else None


def extract_constraints(text: str) -> ExtractedConstraints:
    """Extract structured hardware search constraints from normalized text."""
    constraints = ExtractedConstraints()

    # Location
    m_loc = LOCATION_REGEX.search(text)
    if m_loc:
        raw_loc = m_loc.group(1).upper()
        if "TỦ 1" in raw_loc or "TU 1" in raw_loc:
            constraints.location = "Tủ 1"
        elif "CSW" in raw_loc:
            constraints.location = "CSW"
        elif "EBS" in raw_loc:
            constraints.location = "EBS_LAB"
        else:
            constraints.location = m_loc.group(1)

    # Geometry
    m_geom = GEOMETRY_REGEX.search(text)
    if m_geom:
        raw_g = m_geom.group(1).lower()
        if "góc vuông" in raw_g or "right" in raw_g or "r/a" in raw_g or "ra" in raw_g:
            constraints.geometry = "R/A"
        elif "smd" in raw_g:
            constraints.geometry = "SMD"
        else:
            constraints.geometry = raw_g

    # Size
    m_size = SIZE_REGEX.search(text)
    if m_size:
        try:
            constraints.size_mm = float(m_size.group(1))
        except ValueError:
            pass

    # Pins
    m_pin = PIN_REGEX.search(text)
    if m_pin:
        try:
            constraints.pins = int(m_pin.group(1))
        except ValueError:
            pass

    # Category
    m_cat = CATEGORY_REGEX.search(text)
    if m_cat:
        raw_cat = m_cat.group(1).lower()
        if "connector/cable" in text.lower() or ("connector" in text.lower() and "cable" in text.lower()):
            constraints.category = "Connector/Cable"
        elif "connector" in raw_cat or "đầu nối" in raw_cat:
            constraints.category = "Connector"
        elif "board" in raw_cat or "mạch" in raw_cat:
            constraints.category = "Board"
        elif "sensor" in raw_cat or "cảm biến" in raw_cat:
            constraints.category = "Sensor"
        elif "cable" in raw_cat or "cáp" in raw_cat:
            constraints.category = "Cable"
        elif "switch" in raw_cat or "công tắc" in raw_cat:
            constraints.category = "Switch"
        else:
            constraints.category = raw_cat

    # Color
    m_col = COLOR_REGEX.search(text)
    if m_col:
        raw_col = m_col.group(1).lower()
        if "đen" in raw_col or "black" in raw_col:
            constraints.color = "đen"
        elif "trắng" in raw_col or "white" in raw_col:
            constraints.color = "trắng"
        elif "vàng" in raw_col or "yellow" in raw_col:
            constraints.color = "vàng"
        elif "tím" in raw_col or "purple" in raw_col:
            constraints.color = "tím"
        elif "đỏ" in raw_col or "red" in raw_col:
            constraints.color = "đỏ"

    # Gender
    m_gen = GENDER_REGEX.search(text)
    if m_gen:
        raw_gen = m_gen.group(1).lower()
        if any(k in raw_gen for k in ["female", "cái"]):
            constraints.gender = "female"
        elif any(k in raw_gen for k in ["male", "đực"]):
            constraints.gender = "male"

    # Strip project phrase, date ranges, quantities and borrow verbs before extracting hardware keywords
    clean_kw_text = re.sub(r"(?:cho\s+)?(?:project|dự\s*án)\s+[A-Za-z0-9_\-\.]+", "", text, flags=re.IGNORECASE)
    clean_kw_text = re.sub(r"từ\s+.*?(?:đến|tới|-)\s+[^,.\n]+", "", clean_kw_text, flags=re.IGNORECASE)
    clean_kw_text = re.sub(r"\b\d+\s*(?:cái|chiếc|bộ|con|pcs|món)?\b", "", clean_kw_text, flags=re.IGNORECASE)
    clean_kw_text = re.sub(r"\b(?:mượn|cần\s*mượn|muốn\s*mượn|trả|hoàn\s*trả)\b", "", clean_kw_text, flags=re.IGNORECASE)
    raw_tokens = re.findall(r"[A-Za-z0-9_À-ỹ]+", clean_kw_text.lower())
    stop_words = {
        "cho", "mình", "xem", "danh", "sách", "tìm", "kiếm", "các", "có", "ở", "trong",
        "tủ", "bao", "nhiêu", "cái", "thế", "nào", "gì", "không", "những", "thông", "tin",
        "với", "và", "hoặc", "là", "đang", "còn", "cần", "muốn", "kho", "thiết", "bị",
        "phù", "hợp", "để", "làm", "loại", "như", "xin", "biết", "hiện", "tại", "này",
        "đó", "ra", "sao", "giúp", "vậy", "nhỉ", "ạ", "nhé", "được", "khoảng", "tầm",
        "chiếc", "bộ", "con", "item", "items", "thì", "khi", "sử", "dụng", "hãy",
        "vui", "lòng", "hộ", "máy", "đồ", "ai", "nào", "chỉ", "thôi", "hỏi", "hãy",
        "món", "thứ", "của", "tôi", "em", "bác", "project", "dự", "án",
        "sắp", "hết", "ít", "thấp", "cạn", "cục", "từ", "đến", "tới", "ngày", "mai",
        "tuần", "sau", "cuối", "màu", "đỏ", "đen", "trắng", "vàng", "tím", "nếu",
        "tạo", "lập", "đăng", "ký", "đi",
    }
    keywords = [w for w in raw_tokens if w not in stop_words and len(w) > 1]
    constraints.keywords = keywords

    return constraints


class QueryRouter:
    """Deterministic & LLM-assisted Router for Equipment Management intents."""

    @staticmethod
    def _match_catalog_equipment(text: str) -> Optional[Tuple[str, str]]:
        """Look for exact equipment names appearing in the natural language text."""
        try:
            from app.repositories.factory import get_equipment_repo
            all_eq = get_equipment_repo().list_all()
            t_low = text.lower()
            all_eq_sorted = sorted(all_eq, key=lambda x: len(x.equipment_name), reverse=True)
            for eq in all_eq_sorted:
                name_clean = eq.equipment_name.lower().strip()
                if len(name_clean) >= 4 and name_clean in t_low:
                    return (eq.equipment_id, eq.equipment_name)
        except Exception:
            pass
        return None

    def route_message(self, raw_message: str, state: ConversationState) -> QueryPlan:
        """Parse natural language message into a validated QueryPlan."""
        # 1. Normalize
        norm_text = normalize_whitespace(raw_message)
        norm_text = normalize_equipment_ids(norm_text)
        norm_text = normalize_units(norm_text)
        lower_text = norm_text.lower()

        plan = QueryPlan(
            intent=IntentType.UNKNOWN,
            intent_confidence=1.0,
            raw_message=raw_message,
        )

        # 2. Extract basic flags & entities
        plan.negate_borrow = check_negate_borrow(lower_text)
        plan.ask_auto_approve = check_ask_auto_approve(lower_text)
        plan.is_next_page = check_next_page(lower_text)
        plan.is_pronoun_reference = check_pronoun_reference(lower_text)
        plan.ordinal_index = extract_ordinal(lower_text)
        plan.entity_id = extract_equipment_id(norm_text)
        plan.target_request_id = extract_request_id(norm_text)
        plan.constraints = extract_constraints(norm_text)

        if not plan.entity_id:
            cat_match = self._match_catalog_equipment(norm_text)
            if cat_match:
                plan.entity_id = cat_match[0]
                plan.entity_name = cat_match[1]

        # Check explicit cancellation when there is an active pending action or user says xem thôi/hủy
        is_cancel_words = any(w in lower_text for w in [
            "hủy bỏ", "không mượn nữa", "không trả nữa", "chỉ xem thôi", "mình muốn xem thôi", "xem thôi",
            "thôi không mượn", "thôi không trả", "thôi không cần", "hủy thao tác", "dừng lại"
        ]) or lower_text.strip() in ["hủy", "thôi", "cancel", "bỏ", "dừng"]

        if (state.pending_action or state.pending_form) and is_cancel_words:
            plan.intent = IntentType.CANCEL_ACTION
            return plan
        elif is_cancel_words and any(w in lower_text for w in ["không mượn", "không trả", "xem thôi", "hủy thao tác", "hủy bỏ"]):
            plan.intent = IntentType.CANCEL_ACTION
            return plan

        # 3. Context & Entity Resolution
        # 3.1 Ordinal resolution ("cái thứ 2", "đơn thứ 1")
        if plan.ordinal_index is not None and state.last_result_set:
            resolved_item = state_manager.get_item_by_ordinal(state, plan.ordinal_index)
            if resolved_item:
                if (
                    state.last_result_type == "borrowed_loans"
                    or state.pending_action in ["return", "return_select"]
                    or any(w in lower_text for w in ["trả", "hoàn trả"])
                ):
                    plan.intent = IntentType.RETURN_REQUEST
                    plan.target_request_id = _extract_int_req_id(resolved_item)
                    return plan
                elif state.pending_action == "borrow_select":
                    plan.intent = IntentType.REQUEST_CREATE
                    plan.entity_id = str(resolved_item.get("EquipmentID") or resolved_item.get("equipment_id") or "")
                    plan.entity_name = str(resolved_item.get("EquipmentName") or resolved_item.get("equipment_name") or "")
                    return plan
                elif state.last_result_type in ["request", "user_requests", "overdue_loans", "active_loans"]:
                    plan.intent = IntentType.REQUEST_DETAIL
                    plan.target_request_id = _extract_int_req_id(resolved_item)
                    return plan
                elif state.last_result_type == "equipment":
                    if any(w in lower_text for w in ["bao nhiêu", "mấy cái", "số lượng", "còn không", "còn bao nhiêu"]):
                        plan.intent = IntentType.EQUIPMENT_COUNT
                    else:
                        plan.intent = IntentType.EQUIPMENT_DETAIL
                    plan.entity_id = str(resolved_item.get("EquipmentID") or resolved_item.get("equipment_id") or "")
                    plan.entity_name = str(resolved_item.get("EquipmentName") or resolved_item.get("equipment_name") or "")
                    return plan
                elif any(w in lower_text for w in ["đơn", "request", "yêu cầu", "project", "dự án"]):
                    plan.intent = IntentType.REQUEST_DETAIL
                    plan.target_request_id = _extract_int_req_id(resolved_item)
                    return plan
                elif any(w in lower_text for w in ["cái", "thiết bị", "con"]):
                    if any(w in lower_text for w in ["bao nhiêu", "mấy cái", "số lượng", "còn không", "còn bao nhiêu"]):
                        plan.intent = IntentType.EQUIPMENT_COUNT
                    else:
                        plan.intent = IntentType.EQUIPMENT_DETAIL
                    plan.entity_id = str(resolved_item.get("EquipmentID") or resolved_item.get("equipment_id") or "")
                    plan.entity_name = str(resolved_item.get("EquipmentName") or resolved_item.get("equipment_name") or "")
                    return plan

        # 3.2 Group & Reference Resolvers
        # 3.2.1 Group reference to borrowers/people ("những người đó là ai", "những người đó", "mấy người đó", "họ là ai", "những người nào bị xung đột")
        is_group_people = (
            any(p in lower_text for p in [
                "những người đó", "mấy người đó", "các người đó", "những người này", "mấy người này",
                "các người này", "họ là ai", "những ai vậy", "danh sách người đó", "danh sách những người đó",
                "người đó là ai", "những ai đang mượn", "những người mượn đó", "ai đang mượn các đơn đó",
                "những ai mượn", "ai mượn vậy", "ai đang giữ vậy", "ai vậy", "những người mượn này",
                "những người nào bị xung đột", "ai bị xung đột", "những người bị xung đột", "người bị xung đột"
            ])
            or (
                any(w in lower_text for w in ["người đó", "mấy người", "những người", "những ai", "họ", "người nào"])
                and any(w in lower_text for w in ["là ai", "danh sách", "ai", "thế", "nào", "xung đột"])
            )
        )
        if is_group_people:
            plan.is_group_reference = True
            if state.last_result_type == "overdue_loans" or state.last_intent == IntentType.OVERDUE_LOANS:
                plan.intent = IntentType.OVERDUE_BORROWERS
                return plan
            elif state.last_result_type in ["active_loans", "active_borrowers"] or state.last_intent in [IntentType.ACTIVE_LOANS, IntentType.ACTIVE_BORROWERS]:
                plan.intent = IntentType.ACTIVE_BORROWERS
                return plan
            elif state.last_result_type in ["schedule_conflicts", "conflict_pairs"] or state.last_intent == IntentType.SCHEDULE_CONFLICTS:
                plan.intent = IntentType.CONFLICT_BORROWERS
                return plan
            elif state.last_result_type == "request" and state.last_result_set:
                plan.intent = IntentType.ACTIVE_BORROWERS
                return plan

        # 3.2.2 Group reference to requests ("các đơn trên", "những đơn trên", "các request trên", "mấy đơn đó", "các đơn đó")
        is_group_requests = any(p in lower_text for p in [
            "các đơn trên", "những đơn trên", "các request trên", "những đơn này", "các đơn này",
            "những đơn đó", "mấy đơn đó", "các đơn đó", "danh sách đơn trên", "mấy request trên"
        ])
        if is_group_requests and state.last_result_set:
            plan.is_group_reference = True
            if state.last_result_type in ["request", "user_requests", "overdue_loans", "active_loans"]:
                plan.intent = IntentType.RECENT_REQUESTS
                return plan

        # 3.2.3 Expand detail ("cho mình xem chi tiết hơn", "xem chi tiết hơn", "chi tiết hơn", "xem chi tiết")
        is_expand_detail = any(p in lower_text for p in [
            "cho mình xem chi tiết hơn", "xem chi tiết hơn", "chi tiết hơn", "xem chi tiết", "thông tin chi tiết hơn"
        ])
        if is_expand_detail:
            plan.is_expand_detail = True
            if state.last_result_type in ["request", "user_requests", "overdue_loans", "active_loans"] or state.active_request:
                plan.intent = IntentType.REQUEST_DETAIL
                plan.target_request_id = _extract_int_req_id(state.active_request or state.last_selected_item)
                return plan
            elif state.last_result_type == "equipment" or state.active_equipment:
                plan.intent = IntentType.EQUIPMENT_DETAIL
                if state.active_equipment:
                    plan.entity_id = state.active_equipment.get("EquipmentID")
                elif state.last_selected_item:
                    plan.entity_id = state.last_selected_item.get("EquipmentID")
                return plan

        # 3.2.4 Pronoun reference to request ("đơn này", "yêu cầu này", "request này")
        has_manager_action = any(w in lower_text for w in [
            "duyệt", "approve", "phê duyệt", "từ chối", "reject", "bác bỏ",
            "đổi", "mức ưu tiên", "priority", "thay đổi"
        ])
        if any(p in lower_text for p in ["đơn này", "yêu cầu này", "request này"]):
            if state.active_request or (state.last_result_type in ["request", "user_requests", "overdue_loans", "active_loans"] and state.last_selected_item):
                plan.is_pronoun_reference = True
                plan.target_request_id = _extract_int_req_id(state.active_request or state.last_selected_item)
                if not has_manager_action:
                    plan.intent = IntentType.REQUEST_DETAIL
                    return plan

        # 3.2.5 Pronoun reference to equipment ("thiết bị đó", "thiết bị này", "món đó", "món này")
        if any(p in lower_text for p in ["thiết bị đó", "thiết bị này", "món đó", "món này"]):
            active_eq = state.active_equipment or (state.last_selected_item if state.last_result_type == "equipment" else None)
            if active_eq:
                plan.intent = IntentType.EQUIPMENT_DETAIL
                plan.is_pronoun_reference = True
                plan.entity_id = active_eq.get("EquipmentID")
                return plan

        # 3.3 Check general catalog list query first
        if any(p in lower_text for p in [
            "danh sách trong kho", "các danh sách trong kho", "danh sách thiết bị",
            "tất cả thiết bị", "toàn bộ thiết bị", "trong kho có gì", "có những gì trong kho",
            "kho có gì", "kho đang có gì", "trong kho đang có gì", "trong kho có những gì",
            "trong kho đang có những gì", "trong kho có những món gì", "trong kho đang có những món gì",
            "kho có những món gì", "kho đang có những món gì", "trong kho có những thiết bị gì",
            "trong kho đang có những thiết bị gì", "kho có những thiết bị gì", "kho đang có những thiết bị gì",
            "những loại thiết bị nào", "có những loại thiết bị nào", "các loại thiết bị nào",
            "có các loại thiết bị nào", "kho hiện có những loại thiết bị nào",
            "trong kho hiện có những loại thiết bị nào",
        ]) or (
            any(w in lower_text for w in ["kho", "trong kho"])
            and any(w in lower_text for w in ["có những", "đang có", "hiện có", "có các"])
            and any(w in lower_text for w in ["món gì", "thiết bị gì", "loại thiết bị nào", "gì"])
        ):
            plan.intent = IntentType.EQUIPMENT_SEARCH
            plan.entity_id = None
            plan.entity_name = None
            plan.constraints = ExtractedConstraints()
            return plan

        # 3.2.0.1 Check out-of-stock inventory report (strictly Quantity == 0)
        is_out_of_stock = (
            "sắp hết" not in lower_text
            and (
                any(p in lower_text for p in [
                    "hết trong kho", "đã hết hàng", "hết hàng", "còn 0 cái", "hết sạch", "hết rồi không",
                    "thiết bị nào hết", "món nào hết", "đã hết", "hết rồi", "hết chưa", "tồn bằng 0", "số lượng bằng 0"
                ])
                or (
                    any(w in lower_text for w in ["kho", "trong kho", "thiết bị", "món"])
                    and any(w in lower_text for w in ["hết hàng", "hết rồi", "còn 0 cái", "hết sạch", "nào hết"])
                )
            )
        ) and not plan.entity_id and not any(w in lower_text for w in ["mượn", "borrow", "trả", "return"])

        if is_out_of_stock:
            plan.intent = IntentType.OUT_OF_STOCK_INVENTORY
            plan.entity_id = None
            plan.entity_name = None
            plan.constraints.keywords = []
            return plan

        # 3.2.0.2 Check low-stock inventory report
        is_low_stock = (
            any(p in lower_text for p in [
                "sắp hết", "còn ít", "tồn thấp", "số lượng tồn thấp", "cần bổ sung", "sắp cạn", "tồn kho thấp",
            ])
            or (
                any(w in lower_text for w in ["kho", "trong kho", "thiết bị", "món"])
                and any(w in lower_text for w in ["sắp hết", "còn ít", "cần bổ sung", "sắp cạn"])
            )
            or bool(re.search(r"(?:dưới|còn dưới)\s+(\d+)\s*(?:cái|chiếc|món|bộ)?", lower_text))
            or bool(re.search(r"(\d+)\s*(?:cái|chiếc|món|bộ)?\s*trở\s*xuống", lower_text))
            or bool(re.search(r"không\s*quá\s*(\d+)", lower_text))
        )
        if is_low_stock and not plan.entity_id and not any(w in lower_text for w in ["mượn", "borrow", "trả", "return"]):
            plan.intent = IntentType.LOW_STOCK_INVENTORY
            plan.entity_id = None
            plan.entity_name = None
            plan.constraints.keywords = []

            m_strict = re.search(r"(?:còn\s+)?dưới\s+(\d+)", lower_text)
            m_inc = re.search(r"(\d+)\s*(?:cái|chiếc|món|bộ)?\s*trở\s*xuống", lower_text)
            m_no_more = re.search(r"không\s*quá\s*(\d+)", lower_text)

            if m_strict:
                plan.low_stock_threshold = int(m_strict.group(1))
                plan.low_stock_operator = "<"
            elif m_inc:
                plan.low_stock_threshold = int(m_inc.group(1))
                plan.low_stock_operator = "<="
            elif m_no_more:
                plan.low_stock_threshold = int(m_no_more.group(1))
                plan.low_stock_operator = "<="
            else:
                plan.low_stock_threshold = None
                plan.low_stock_operator = None
            return plan

        # 3.2.1 Check existence inquiry: "Kho có CANInterface XYZ không?", "Kho có TU1-001 không?"
        is_exist, exist_target = check_existence_query(norm_text)
        if is_exist and exist_target:
            eq_id_match = extract_equipment_id(exist_target)
            if eq_id_match:
                plan.entity_id = eq_id_match
                plan.entity_name = eq_id_match
            else:
                plan.entity_id = None
                plan.entity_name = exist_target
            plan.intent = IntentType.EQUIPMENT_EXISTS
            plan.constraints = extract_constraints(exist_target)
            return plan

        # 3.3 Match against previous result set options if message is a clarification (e.g. "10.3MP")
        if not plan.entity_id and state.last_result_set and state.last_result_type == "equipment":
            norm_q = re.sub(r"[\s\-_.,/()]+", "", lower_text)
            for it in state.last_result_set:
                it_id_norm = re.sub(r"[\s\-_.,/()]+", "", str(it.get("EquipmentID") or it.get("equipment_id") or "").lower())
                it_name_norm = re.sub(r"[\s\-_.,/()]+", "", str(it.get("EquipmentName") or it.get("equipment_name") or "").lower())
                if (norm_q in it_name_norm or norm_q in it_id_norm) and len(norm_q) >= 3:
                    plan.entity_id = str(it.get("EquipmentID") or it.get("equipment_id"))
                    plan.entity_name = str(it.get("EquipmentName") or it.get("equipment_name"))
                    if state.last_intent in [IntentType.EQUIPMENT_COUNT, IntentType.AVAILABILITY_QUERY, IntentType.EQUIPMENT_DETAIL]:
                        plan.intent = state.last_intent
                        return plan
                    break

        # 3.4 Pronoun and Follow-up context resolution ("nó", "thiết bị này", "đơn này")
        is_followup_question = any(w in lower_text for w in [
            "còn bao nhiêu", "ở đâu", "vị trí", "thông tin gì", "dùng để làm gì",
            "có đủ", "đủ không", "còn đủ", "đơn này", "đơn thứ", "mức ưu tiên gì"
        ])
        has_new_subject = bool(plan.constraints.keywords or plan.constraints.category or plan.constraints.location or plan.constraints.geometry or plan.constraints.size_mm or plan.constraints.color)

        if plan.is_pronoun_reference or (not plan.entity_id and not plan.target_request_id and not plan.ordinal_index and is_followup_question and not has_new_subject):
            if "đơn" in lower_text or "request" in lower_text or state.last_result_type in ["request", "user_requests", "overdue_loans", "active_loans"]:
                if not plan.target_request_id and state.active_request:
                    plan.target_request_id = _extract_int_req_id(state.active_request)
                elif not plan.target_request_id and state.active_request_ids:
                    plan.target_request_id = state.active_request_ids[0]
            else:
                if not plan.entity_id and state.active_equipment:
                    plan.entity_id = str(state.active_equipment.get("EquipmentID") or state.active_equipment.get("equipment_id") or "")
                    plan.entity_name = str(state.active_equipment.get("EquipmentName") or state.active_equipment.get("equipment_name") or "")
                elif not plan.entity_id and state.active_equipment_ids:
                    plan.entity_id = state.active_equipment_ids[0]

        # 4. Check Pagination continuation
        if plan.is_next_page:
            if state.last_result_type == "equipment":
                plan.intent = IntentType.EQUIPMENT_SEARCH
            elif state.last_result_type in ["request", "overdue_loans", "active_loans"]:
                plan.intent = IntentType.RECENT_REQUESTS
            else:
                plan.intent = IntentType.PENDING_REQUEST_LIST
            return plan

        # 5. Extract form fields if present
        form_data = extract_borrow_fields(norm_text)
        if "quantity" in form_data:
            plan.quantity = form_data["quantity"]
        if "needed_from" in form_data:
            plan.needed_from = form_data["needed_from"]
        if "needed_to" in form_data:
            plan.needed_to = form_data["needed_to"]
        if "project" in form_data:
            plan.project = form_data["project"]
        if "purpose" in form_data:
            plan.purpose = form_data["purpose"]
        if "condition_notes" in form_data:
            plan.condition_notes = form_data["condition_notes"]

        # 6. Intent classification logic

        # 6.1 Priority Inquiry (Request domain)
        is_prio_inquiry = (
            any(p in lower_text for p in ["đề xuất mức ưu tiên gì", "mức ưu tiên gì", "priority gì", "độ ưu tiên gì", "ưu tiên gì", "priority nào", "mức ưu tiên nào", "lý do ai"])
            or ("ai đề xuất" in lower_text and "ưu tiên" in lower_text)
        )
        if is_prio_inquiry:
            plan.intent = IntentType.REQUEST_DETAIL
            return plan

        # 6.2 Priority Review (Manager mutation)
        is_prio_change = (
            any(p in lower_text for p in ["đổi priority", "đổi độ ưu tiên", "chỉnh priority", "cập nhật priority", "sửa độ ưu tiên", "thay đổi priority", "set priority"])
            or ("thành " in lower_text and any(pl in lower_text for pl in ["high", "medium", "low", "critical", "needs review"]))
        )
        if is_prio_change:
            m_prio = re.search(r"\b(critical|high|medium|low|needs review)\b", lower_text)
            if m_prio:
                raw_prio = m_prio.group(1).title()
                if raw_prio == "Needs Review":
                    raw_prio = "Needs review"
                plan.new_priority = raw_prio
            plan.intent = IntentType.PRIORITY_REVIEW
            return plan

        # 6.3 My Requests Queries (User Request Domain - Query, not creation)
        is_my_requests = (
            any(p in lower_text for p in [
                "yêu cầu mượn của tôi", "yêu cầu mượn của mình", "yêu cầu của tôi", "yêu cầu của mình",
                "đơn mượn của tôi", "đơn mượn của mình", "đơn của tôi", "đơn của mình",
                "trạng thái các yêu cầu", "trạng thái yêu cầu", "trạng thái đơn",
                "các yêu cầu tôi đã gửi", "yêu cầu tôi đã gửi", "các đơn tôi đã gửi", "đơn tôi đã gửi",
                "tôi đã gửi", "mình đã gửi",
                "danh sách yêu cầu của tôi", "danh sách đơn của tôi", "danh sách yêu cầu mượn",
                "đơn nào của tôi", "yêu cầu nào của tôi", "các yêu cầu của tôi", "các đơn của tôi",
                "tôi đang mượn những thiết bị nào", "tôi đang mượn thiết bị nào", "mình đang mượn những thiết bị nào",
                "tôi đang mượn gì", "mình đang mượn gì", "thiết bị tôi đang mượn", "thiết bị mình đang mượn",
                "xem yêu cầu của tôi", "xem đơn của tôi", "xem đơn mượn của tôi", "cho tôi biết các yêu cầu tôi đã gửi",
                "tôi đã mượn", "mình đã mượn", "các yêu cầu đã gửi",
                "hiện mình đang mượn mấy thiết bị", "mình đang mượn mấy thiết bị", "tôi đang mượn mấy thiết bị",
                "hiện tôi đang mượn mấy thiết bị", "mình mượn mấy thiết bị", "tôi mượn mấy thiết bị",
                "hiện mình đang mượn", "hiện tôi đang mượn", "mình đang mượn mấy", "tôi đang mượn mấy",
                "mình đang mượn những gì", "tôi đang mượn những gì", "mình đang mượn", "tôi đang mượn",
            ])
            or (
                any(w in lower_text for w in ["yêu cầu", "đơn", "request"])
                and any(w in lower_text for w in ["của tôi", "của mình", "tôi gửi", "mình gửi", "tôi tạo", "mình tạo"])
                and not any(w in lower_text for w in ["tạo đơn", "muốn mượn", "cần mượn thêm", "lập đơn", "tạo mới"])
            )
            or (
                (state.last_result_type in ["user_requests", "request"] or state.last_intent == IntentType.MY_REQUESTS)
                and any(p in lower_text for p in [
                    "đã được duyệt", "đã duyệt", "còn chờ duyệt", "còn chờ", "chưa duyệt", "bị từ chối", "đang mượn"
                ])
                and not any(w in lower_text for w in ["ai cần", "quản lý", "duyệt đơn", "từ chối"])
            )
        )
        if is_my_requests:
            if any(w in lower_text for w in ["đã được duyệt", "đã duyệt", "được duyệt", "approved"]):
                plan.status_filter = "Approved"
            elif any(w in lower_text for w in ["chờ duyệt", "còn chờ", "đang chờ", "chưa duyệt", "pending"]):
                plan.status_filter = "Pending"
            elif any(w in lower_text for w in ["đang mượn", "đang giữ", "chưa trả", "borrowed", "mấy thiết bị"]):
                plan.status_filter = "Borrowed"
            elif any(w in lower_text for w in ["bị từ chối", "từ chối", "rejected", "bác bỏ"]):
                plan.status_filter = "Rejected"
            else:
                plan.status_filter = None
            plan.intent = IntentType.MY_REQUESTS
            return plan

        # 6.3.2 Person refinement follow-up: "Nếu chỉ riêng Nam Phạm thôi thì sao", "riêng Nam Phạm", "chỉ riêng Nam Phạm"
        m_person = re.search(r"(?:nếu\s+)?(?:chỉ\s+)?riêng\s+([A-Za-zÀ-ỹ\s]+?)(?:\s+thôi)?(?:\s+thì\s+sao)?\??$", lower_text)
        if m_person and (
            state.last_result_type in ["user_requests", "active_loans", "active_borrowers"]
            or state.last_intent in [IntentType.MY_REQUESTS, IntentType.ACTIVE_LOANS, IntentType.ACTIVE_BORROWERS, IntentType.ACTIVE_BORROWERS_COUNT]
        ):
            target_person_name = m_person.group(1).strip()
            plan.intent = IntentType.MY_REQUESTS if state.last_result_type == "user_requests" else IntentType.ACTIVE_LOANS
            plan.entity_name = target_person_name
            plan.status_filter = "Borrowed"
            return plan

        # 6.3.3 List equipment details follow-up: "Những thiết bị đó là gì", "Các thiết bị đó là gì"
        if any(p in lower_text for p in [
            "những thiết bị đó là gì", "các thiết bị đó là gì", "thiết bị đó là gì",
            "gồm những thiết bị nào", "những món đó là gì", "cụ thể là những thiết bị nào"
        ]) and state.last_result_set:
            if state.last_result_type in ["user_requests", "borrowed_loans"] or state.last_intent == IntentType.MY_REQUESTS:
                plan.intent = IntentType.MY_REQUESTS
                plan.status_filter = "Borrowed"
                return plan
            elif state.last_result_type in ["active_loans", "active_borrowers"]:
                plan.intent = IntentType.ACTIVE_LOANS
                return plan

        # 6.4 Return Request — MUST be before borrow keyword check
        is_hypothetical_or_capability = any(p in lower_text for p in [
            "sau khi trả", "nếu phát hiện", "có thể báo cho quản lý", "hệ thống có thể", "có thể báo", "khi phát hiện", "báo cho quản lý không"
        ])
        is_return_kw = (
            any(p in lower_text for p in [
                "muốn trả đồ", "muốn trả lại", "trả thiết bị", "hoàn trả thiết bị",
                "trả đồ", "tôi muốn trả", "mình muốn trả", "trả lại thiết bị",
                "trả lại đồ", "muốn trả", "tôi trả", "mình trả", "hoàn trả",
            ])
            and not any(p in lower_text for p in [
                "trả trễ", "trả muộn", "quá hạn trả", "chậm trả", "trả thiết bị trễ",
                "khi nào trả", "thời gian trả", "bao giờ trả", "lúc nào trả",
            ])
            and not is_hypothetical_or_capability
        )
        if is_return_kw:
            plan.intent = IntentType.RETURN_REQUEST
            return plan

        # 6.3.4 Hypothetical follow-up inquiry on equipment sufficiency/availability:
        # e.g. "Nếu mình cần mượn 30 cái thì sao?", "Nếu chỉ mượn 5 cái thì sao?", "30 cái thì sao?"
        m_hypo_qty = re.search(r"(?:nếu\s+)?(?:mình\s+|tôi\s+|em\s+)?(?:chỉ\s+)?(?:cần\s+|muốn\s+|lấy\s+)?(?:mượn\s+)?(\d+)\s*(?:cái|chiếc|con|bộ)?(?:\s+thì\s+sao|\s+được\s+không|\s+có\s+đủ\s+không|\s+đủ\s+không|\s+còn\s+dư\s+không)?\??$", lower_text)
        if m_hypo_qty and (state.active_equipment or state.active_equipment_ids) and any(w in lower_text for w in ["thì sao", "được không", "đủ không", "nếu", "chỉ"]):
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
                    return plan
            except (ValueError, IndexError):
                pass

        # 6.4b Approve Request (Manager action)
        is_borrow_kw = (
            any(p in lower_text for p in ["mượn", "tạo đơn", "đăng ký mượn", "cần mượn", "borrow"])
            and not is_my_requests
            and "thì sao" not in lower_text
            and not any(q in lower_text for q in [
                "mượn gì", "mượn cái gì", "mượn thiết bị gì", "ai mượn", "ai đang mượn",
                "yêu cầu của tôi", "đơn của tôi", "của tôi", "của mình", "tôi đang mượn",
                "đủ không", "có đủ", "còn đủ", "đáp ứng đủ", "ai đang dùng", "ai đang sử dụng",
                "ai sử dụng", "còn dư", "dư không"
            ])
        )
        is_approve = (
            any(p in lower_text for p in [
                "duyệt đơn", "duyệt yêu cầu", "duyệt request", "phê duyệt", "đồng ý đơn",
                "chấp thuận đơn", "chấp thuận yêu cầu", "chấp thuận", "approve"
            ])
            or (lower_text.strip() == "duyệt" or lower_text.startswith("duyệt ") or "duyệt nó" in lower_text)
        ) and not is_borrow_kw
        if is_approve:
            plan.intent = IntentType.APPROVE_REQUEST
            return plan

        # 6.4 Reject Request (Manager action)
        is_reject = any(p in lower_text for p in [
            "từ chối", "bác bỏ", "không duyệt", "reject", "hủy duyệt"
        ])
        if is_reject:
            plan.intent = IntentType.REJECT_REQUEST
            m_reason = re.search(r"(?:vì|do|lý do|bởi vì)\s+([^,\.\n]+)", lower_text)
            if m_reason:
                plan.reject_reason = m_reason.group(1).strip()
            return plan

        # 6.5 Manager Request Domain Specific Queries
        # 6.5.1 Pending requests count
        if (
            any(w in lower_text for w in ["chờ duyệt", "pending", "cần duyệt", "cần mình duyệt", "chưa duyệt"])
            and any(c in lower_text for c in ["bao nhiêu", "mấy đơn", "số lượng", "có bao nhiêu", "mấy cái đơn", "mấy"])
        ):
            plan.intent = IntentType.PENDING_REQUEST_COUNT
            return plan

        # 6.5.2 Pending requests list
        if any(p in lower_text for p in ["chờ duyệt", "đơn pending", "cần duyệt", "chưa duyệt", "chờ phê duyệt"]):
            plan.intent = IntentType.PENDING_REQUEST_LIST
            return plan

        # 6.5.3 Overdue loans
        is_overdue = any(p in lower_text for p in [
            "trả thiết bị trễ", "trả trễ", "quá hạn", "trễ hạn", "trả muộn", "chậm trả", "quá hạn trả"
        ])
        if is_overdue:
            plan.intent = IntentType.OVERDUE_LOANS
            return plan

        # 6.5.4 Active borrowers COUNT (before list)
        is_borrowers_count = any(p in lower_text for p in [
            "bao nhiêu người đang mượn", "có mấy người mượn", "bao nhiêu người mượn",
            "có bao nhiêu người đang mượn", "mấy người đang mượn",
        ])
        if is_borrowers_count:
            plan.intent = IntentType.ACTIVE_BORROWERS_COUNT
            return plan

        # 6.5.5 Active borrowers LIST
        is_borrowers = any(p in lower_text for p in [
            "ai đang mượn", "ai mượn thiết bị", "người đang mượn", "ai đang giữ", "danh sách người mượn"
        ])
        if is_borrowers:
            plan.intent = IntentType.ACTIVE_BORROWERS
            return plan

        # 6.5.6 Active loans COUNT (before list)
        is_active_loans_count = any(p in lower_text for p in [
            "bao nhiêu thiết bị đang được mượn", "có mấy cái đang mượn",
            "bao nhiêu thiết bị đang mượn", "có bao nhiêu thiết bị đang được mượn",
            "bao nhiêu lượt mượn", "bao nhiêu đơn đang mượn",
        ])
        if is_active_loans_count:
            plan.intent = IntentType.ACTIVE_LOANS_COUNT
            return plan

        # 6.5.7 Active loans LIST
        is_active_loans = any(p in lower_text for p in [
            "thiết bị nào đang được mượn", "thiết bị nào đang mượn", "các thiết bị đang được mượn",
            "các thiết bị đang mượn", "thiết bị đang cho mượn", "thiết bị nào đang cho mượn",
            "có thiết bị nào đang mượn"
        ])
        if is_active_loans:
            plan.intent = IntentType.ACTIVE_LOANS
            return plan

        # 6.5.6 Schedule conflicts
        is_conflicts = any(p in lower_text for p in [
            "xung đột lịch", "trùng lịch", "trùng ngày mượn", "đơn trùng lịch"
        ])
        if is_conflicts:
            plan.intent = IntentType.SCHEDULE_CONFLICTS
            return plan

        # 6.5.7 Recent single request: "Ai là người request gần đây nhất?", "Đơn nào vừa tạo gần nhất?"
        m_qty = re.search(r"(\d+)\s*(?:request|đơn|yêu cầu)", lower_text)
        has_plural_marker = bool(m_qty) or any(p in lower_text for p in ["các", "danh sách", "những", "top"])
        is_recent_single = (
            any(p in lower_text for p in [
                "request gần đây nhất", "yêu cầu gần đây nhất", "đơn gần đây nhất",
                "vừa tạo gần nhất", "request mới nhất", "đơn mới nhất",
                "ai là người request", "người request gần đây nhất", "người request gần nhất",
                "người request gần đây"
            ])
            or ("ai" in lower_text and "request" in lower_text and any(w in lower_text for w in ["gần đây", "gần nhất", "mới nhất"]))
            or (any(p in lower_text for p in ["request gần nhất", "đơn gần nhất", "yêu cầu gần nhất"]) and not has_plural_marker)
        ) and not has_plural_marker
        if is_recent_single:
            plan.intent = IntentType.RECENT_REQUEST
            return plan

        # 6.5.8 Recent requests list: "Cho mình xem các request gần đây.", "Cho mình xem 5 request gần nhất."
        is_recent_list = (
            bool(m_qty)
            or any(p in lower_text for p in [
                "các request gần đây", "các request gần nhất", "danh sách request gần", "các request",
                "danh sách đơn gần", "các đơn gần đây", "các đơn gần nhất", "đơn mượn gần đây",
                "request gần đây", "request gần nhất", "đơn gần đây"
            ])
            or (
                any(p in lower_text for p in ["request gần", "đơn gần", "yêu cầu gần"])
                and any(c in lower_text for c in ["xem", "cho mình", "danh sách", "các", "liệt kê", "top"])
            )
        )
        if is_recent_list:
            if m_qty:
                plan.quantity = int(m_qty.group(1))
            plan.intent = IntentType.RECENT_REQUESTS
            return plan

        # 6.6 Request detail / follow-up
        is_req_followup = (
            ("đơn" in lower_text or "request" in lower_text or "cái đầu tiên" in lower_text or (state.last_result_type == "request" and state.last_result_set))
            and (
                plan.target_request_id is not None
                or plan.ordinal_index is not None
                or plan.is_pronoun_reference
                or any(w in lower_text for w in ["là ai", "của ai", "project nào", "dự án nào", "mượn gì", "mượn thiết bị gì", "ưu tiên gì", "mấy đơn", "trước đó", "trước đấy"])
            )
        )
        if is_req_followup and not is_borrow_kw:
            plan.intent = IntentType.REQUEST_DETAIL
            return plan

        # 6.7 Unsupported Hardware Queries: Project usage, Return time, Condition, Scheduling
        # 6.6 Cancellation
        if any(p in lower_text for p in ["hủy bỏ", "hủy thao tác", "thôi không cần", "thôi không mượn", "bỏ qua", "dừng lại"]) or lower_text.strip() in ["hủy", "cancel", "thôi", "bỏ"]:
            plan.intent = IntentType.CANCEL_ACTION
            return plan

        # 6.7 Alternative Search
        is_alt_kw = (
            any(p in lower_text for p in [
                "thiết bị thay thế", "thay thế cho", "thay thế được cho", "thay thế được", "thay cho",
                "tìm thiết bị thay thế", "tìm thay thế", "loại nào tương tự", "tương đương với",
                "tương đương", "alternative", "substitute", "đồ thay thế", "món thay thế", "có gì thay thế"
            ])
            or (
                "thay thế" in lower_text
                and any(w in lower_text for w in ["thiết bị", "được cho", "thay cho", "cho", "món", "nào", "có gì", "không"])
            )
            or ("tương tự" in lower_text and any(w in lower_text for w in ["thiết bị", "loại", "món"]))
        )
        if is_alt_kw and not is_borrow_kw:
            plan.intent = IntentType.ALTERNATIVE_SEARCH
            return plan

        # 6.8 External Sourcing
        if any(p in lower_text for p in ["tìm nguồn bên ngoài", "nguồn bên ngoài", "tìm bên ngoài", "mua ngoài", "order ngoài", "external sourcing", "sourcing ngoài", "mua ở ngoài"]):
            plan.intent = IntentType.EXTERNAL_SOURCING
            return plan

        # 6.9 Project usage, Return time, Condition, Scheduling
        if any(p in lower_text for p in ["sắp xếp lịch", "điều phối lịch", "xếp lịch", "sắp xếp lại lịch", "lịch trình mượn"]):
            plan.intent = IntentType.SCHEDULE_PLANNING
            return plan

        if any(p in lower_text for p in ["tình trạng", "còn mới", "hư hỏng", "hỏng hóc", "hỏng không", "hoạt động tốt", "cũ hay mới", "chất lượng", "thiệt hại", "báo hỏng"]):
            plan.intent = IntentType.EQUIPMENT_CONDITION_QUERY
            return plan

        if any(p in lower_text for p in ["khi nào trả", "thời gian trả", "bao giờ trả", "lúc nào trả", "khi nào nhận lại", "bao giờ nhận lại", "khi nào có lại", "nhận lại"]):
            plan.intent = IntentType.USAGE_QUERY
            return plan

        if (plan.entity_id or state.last_result_type == "equipment") and any(p in lower_text for p in ["ai đang dùng", "project nào đang dùng", "dự án nào đang dùng", "dự án nào mượn"]):
            plan.intent = IntentType.PROJECT_USAGE_QUERY
            return plan

        # 6.10 User management (Admin): add user vs list users
        if any(p in lower_text for p in ["thêm user", "tạo user", "thêm người dùng", "tạo người dùng", "thêm tài khoản", "add user"]):
            plan.intent = IntentType.ADD_USER
            return plan

        if any(p in lower_text for p in ["danh sách user", "danh sách người dùng", "xem danh sách user", "list users", "phân quyền", "đổi role", "quản lý user"]):
            plan.intent = IntentType.LIST_USERS
            return plan

        # 6.7 Quantity Sufficiency query: "có đủ không", "đủ không", "còn đủ không", "đáp ứng đủ không", "còn dư không", "có còn dư"
        if any(p in lower_text for p in [
            "có đủ không", "đủ không", "còn đủ không", "đáp ứng đủ không", "kho có đủ không", "có đủ", "còn đủ", "dư không"
        ]):
            plan.intent = IntentType.QUANTITY_SUFFICIENCY
            return plan

        # 6.8 Availability query: "có sẵn không", "khả dụng không", "có ai mượn không", "trùng lịch không", "ai sử dụng không", "ai đang sử dụng", "còn dư trong kho"
        if any(p in lower_text for p in [
            "có sẵn không", "khả dụng", "có ai mượn", "có ai dùng", "có đang được ai sử dụng", "ai đang sử dụng", "ai sử dụng không", "ai đang dùng",
            "trùng lịch", "available", "rảnh không", "còn dư trong kho", "còn dư để"
        ]):
            plan.intent = IntentType.AVAILABILITY_QUERY
            return plan

        # 6.9 Equipment Count query: "có bao nhiêu cái", "còn bao nhiêu cái", "số lượng bao nhiêu", "còn mấy cái", "bao nhiêu loại", "mấy loại"
        if any(p in lower_text for p in [
            "bao nhiêu cái", "còn bao nhiêu", "có bao nhiêu", "số lượng bao nhiêu", "còn mấy cái", "bao nhiêu chiếc", "bao nhiêu con",
            "bao nhiêu loại", "mấy loại", "có bao nhiêu loại", "có mấy loại"
        ]):
            plan.intent = IntentType.EQUIPMENT_COUNT
            return plan

        # 6.10 Borrow / Request Create
        # BUT: Check negation first! "Không cần mượn, chỉ hỏi..."
        if is_borrow_kw and not plan.negate_borrow:
            plan.intent = IntentType.REQUEST_CREATE
            return plan

        # 6.11 If user had a pending borrow form, and provides more form fields
        if state.pending_form and (plan.quantity or plan.needed_from or plan.project or plan.purpose):
            if not plan.negate_borrow:
                plan.intent = IntentType.REQUEST_CREATE
                return plan

        # 6.12 Equipment Detail query: "thông tin về", "thông tin của", "có những thông tin gì", "ở đâu", "vị trí nào", "mô tả", "chi tiết", "dùng để làm gì"
        is_detail_kw = any(p in lower_text for p in [
            "thông tin về", "thông tin của", "thông tin", "thông số", "đặc tính", "profile",
            "thông tin gì", "ở đâu", "vị trí nào", "mô tả", "chi tiết", "dùng để làm gì", "nằm ở đâu", "tủ nào"
        ])
        if plan.entity_id and is_detail_kw:
            plan.intent = IntentType.EQUIPMENT_DETAIL
            return plan

        if any(p in lower_text for p in ["thông tin gì", "ở đâu", "vị trí nào", "mô tả", "chi tiết", "dùng để làm gì", "nằm ở đâu", "tủ nào"]):
            plan.intent = IntentType.EQUIPMENT_DETAIL
            return plan

        # If user explicitly gives an equipment ID and asks about it (e.g. "TU1-001")
        if plan.entity_id and len(lower_text.replace(plan.entity_id.lower(), "").strip()) < 10:
            plan.intent = IntentType.EQUIPMENT_DETAIL
            return plan

        # 6.13 Help: "hướng dẫn", "trợ giúp", "giúp", "bạn làm được gì"
        if any(p in lower_text for p in ["hướng dẫn", "trợ giúp", "bạn làm được gì", "chức năng", "help"]):
            plan.intent = IntentType.HELP
            return plan

        # 6.14 Default to Equipment Search if there are constraints or keywords
        if (
            plan.constraints.category
            or plan.constraints.location
            or plan.constraints.geometry
            or plan.constraints.size_mm
            or plan.constraints.pins
            or plan.constraints.color
            or plan.constraints.gender
            or plan.constraints.keywords
            or "tìm" in lower_text
            or "danh sách" in lower_text
            or "connector" in lower_text
            or "board" in lower_text
        ):
            plan.intent = IntentType.EQUIPMENT_SEARCH
            return plan

        # If completely unrouted, mark UNKNOWN
        plan.intent = IntentType.UNKNOWN
        return plan


# Singleton instance
query_router = QueryRouter()

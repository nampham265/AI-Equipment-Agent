"""Vietnamese message normalizer and entity pattern extractor."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Optional, Tuple


# Regex patterns for equipment IDs like TU1-001, TU2-007, EBS-030, CSW-001, DEMO-EQ-001
EQUIPMENT_ID_PATTERN = re.compile(
    r"\b(TU[0-9]|EBS|CSW|DEMO-EQ)[ _-]?([0-9]{2,4})\b",
    re.IGNORECASE,
)

# Regex pattern for request IDs like REQ-20261004-000001 or REQ-000001 or REQ-1 or đơn #1 or #1
REQUEST_ID_PATTERN = re.compile(
    r"(?:REQ-(?:\d+-)?(\d+)|đơn\s*(?:số\s*|#\s*)?(\d+)|#\s*(\d+))\b",
    re.IGNORECASE,
)

# Regex pattern for ordinal references: "cái thứ 2", "thiết bị thứ 3", "đơn thứ 1", "thứ 2"
ORDINAL_PATTERN = re.compile(
    r"(?:cái|thiết\s*bị|đơn|item|sản\s*phẩm|kết\s*quả)?\s*(?:thứ|số)\s*(\d+)",
    re.IGNORECASE,
)

# Pronoun patterns: "nó", "thiết bị này", "cái này", "cái đó", "đơn này", "request này"
PRONOUN_PATTERN = re.compile(
    r"\b(nó|cái\s*này|cái\s*đó|thiết\s*bị\s*này|thiết\s*bị\s*đó|đơn\s*này|đơn\s*đó|request\s*này)\b",
    re.IGNORECASE,
)

# Pagination patterns: "xem tiếp", "trang sau", "tiếp theo", "hiển thị thêm", "còn nữa không"
NEXT_PAGE_PATTERN = re.compile(
    r"\b(xem\s*tiếp|trang\s*sau|tiếp\s*theo|hiển\s*thị\s*thêm|còn\s*nữa\s*không|cho\s*xem\s*tiếp|xem\s*thêm)\b",
    re.IGNORECASE,
)

# Negation patterns for borrowing: "không cần mượn", "không mượn", "đừng tạo đơn", "chỉ hỏi"
NEGATE_BORROW_PATTERN = re.compile(
    r"\b(không\s*cần\s*mượn|không\s*mượn|đừng\s*tạo\s*đơn|chỉ\s*hỏi\s*thôi|chỉ\s*hỏi|chưa\s*cần\s*mượn|không\s*phải\s*mượn)\b",
    re.IGNORECASE,
)

# Unit pattern: "4.2 mm", "4.2mm", "3 mm", "3mm"
UNIT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mm|cm|m|kg|g|pos|pin|chân|cái|bộ)",
    re.IGNORECASE,
)

# Quantity extraction: "5 cái", "mượn 3 cái", "số lượng 10"
QUANTITY_PATTERN = re.compile(
    r"(?:số\s*lượng|mượn|lấy|cần)?\s*(\d+)\s*(?:cái|bộ|chiếc|con|item|items|pcs|chân|pos)?",
    re.IGNORECASE,
)


def normalize_whitespace(text: str) -> str:
    """Normalize unicode and strip multiple whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def normalize_equipment_ids(text: str) -> str:
    """Standardize equipment IDs in text to uppercase standard: TU1-001, EBS-030, etc."""
    def _repl(m: re.Match) -> str:
        prefix = m.group(1).upper()
        if prefix == "DEMOEQ":
            prefix = "DEMO-EQ"
        num = m.group(2)
        return f"{prefix}-{num}"

    return EQUIPMENT_ID_PATTERN.sub(_repl, text)


def normalize_units(text: str) -> str:
    """Standardize units like '4.2 mm' -> '4.2mm'."""
    def _repl(m: re.Match) -> str:
        val = m.group(1)
        unit = m.group(2).lower()
        return f"{val}{unit}"

    return UNIT_PATTERN.sub(_repl, text)


def extract_equipment_id(text: str) -> Optional[str]:
    """Find first equipment ID in text if any."""
    m = EQUIPMENT_ID_PATTERN.search(text)
    if m:
        prefix = m.group(1).upper()
        num = m.group(2)
        return f"{prefix}-{num}"
    return None


def extract_request_id(text: str) -> Optional[int]:
    """Find request ID (e.g. REQ-20261004-000002 or REQ-2 or đơn #2 or đơn số 2) in text."""
    m = REQUEST_ID_PATTERN.search(text)
    if m:
        val = m.group(1) or m.group(2) or m.group(3)
        if val:
            try:
                return int(val)
            except ValueError:
                pass
    return None


def extract_ordinal(text: str) -> Optional[int]:
    """Extract ordinal index: 'cái thứ 2' -> 2, 'đơn thứ 1' -> 1, 'cái đầu tiên' -> 1."""
    t_low = text.lower()
    if any(w in t_low for w in ["đầu tiên", "thứ nhất", "cái đầu", "đơn đầu"]):
        return 1
    if "thứ hai" in t_low:
        return 2
    if "thứ ba" in t_low:
        return 3
    if "thứ tư" in t_low:
        return 4
    if "thứ năm" in t_low:
        return 5
    m = ORDINAL_PATTERN.search(text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def check_pronoun_reference(text: str) -> bool:
    """Check if message refers to previous active entity using a pronoun."""
    return bool(PRONOUN_PATTERN.search(text))


def check_next_page(text: str) -> bool:
    """Check if message is asking for pagination next page."""
    return bool(NEXT_PAGE_PATTERN.search(text))


def check_negate_borrow(text: str) -> bool:
    """Check if user explicitly negates borrowing intent."""
    return bool(NEGATE_BORROW_PATTERN.search(text))


# Pattern detecting requests for AI to auto-approve: "duyệt luôn", "duyệt hộ", "duyệt giúp"
AUTO_APPROVE_PATTERN = re.compile(
    r"\b(duyệt\s*luôn|duyệt\s*hộ|duyệt\s*giúp|duyệt\s*ngay|phê\s*duyệt\s*luôn|bạn\s*duyệt\s*luôn)\b",
    re.IGNORECASE,
)


def check_ask_auto_approve(text: str) -> bool:
    """Check if user asks AI to auto-approve the request."""
    return bool(AUTO_APPROVE_PATTERN.search(text))


def check_existence_query(text: str) -> Tuple[bool, Optional[str]]:
    """Detect if user is asking whether an equipment exists in stock, and extract target entity.
    
    Examples:
    - 'Kho có CANInterface XYZ không?' -> (True, 'CANInterface XYZ')
    - 'Kho có TU1-001 không?' -> (True, 'TU1-001')
    - 'Có CANInterface XYZ không?' -> (True, 'CANInterface XYZ')
    - 'CANInterface XYZ có trong kho không?' -> (True, 'CANInterface XYZ')
    """
    clean = text.strip()
    clean_low = clean.lower()
    if any(k in clean_low for k in [
        "bao nhiêu", "mấy cái", "mấy chiếc", "mấy đơn", "mấy", "mượn", "đăng ký", "tạo đơn",
        "request", "yêu cầu", "đơn", "quá hạn", "trả trễ", "trễ hạn", "chậm trả", "trả muộn",
        "ai đang", "ai là", "ai", "thì sao", "thế nào", "trước đó", "trước đấy", "gần đây", "gần nhất",
        "thay thế", "tương đương", "thay cho", "nguồn bên ngoài", "mua ngoài",
        "xung đột", "trùng lịch", "lịch", "những món gì", "những thiết bị gì",
        "món gì", "thiết bị gì", "loại thiết bị nào", "loại nào", "những gì"
    ]):
        return False, None

    # Exclude general listing queries
    excluded_cand_terms = {
        "gì", "những gì", "sao", "thế nào",
        "món gì", "những món gì", "những món", "các món gì", "món",
        "thiết bị gì", "những thiết bị gì", "các thiết bị gì", "thiết bị",
        "loại gì", "loại thiết bị gì", "loại thiết bị nào", "những loại thiết bị nào",
        "các loại thiết bị nào", "món nào", "thiết bị nào", "những thứ gì",
    }

    # Pattern 1: Kho có <ENTITY> không? / Có <ENTITY> không?
    m1 = re.search(
        r"^(?:cho\s+(?:mình|em|tôi)\s+(?:hỏi|biết)\s+)?(?:kiểm\s*tra\s+(?:xem\s+)?)?(?:trong\s+)?(?:kho\s+)?(?:có|còn)\s+(?:thiết\s*bị\s+)?(.*?)(?:\s+(?:không|ko|ạ|nhỉ|\?)\s*)*\??$",
        clean,
        re.IGNORECASE,
    )
    if m1 and m1.group(1).strip():
        cand = m1.group(1).strip()
        cand = re.sub(r"^(?:cái|con|bộ)\s+", "", cand, flags=re.IGNORECASE).strip()
        if cand and cand.lower() not in excluded_cand_terms:
            return True, cand

    # Pattern 2: <ENTITY> có trong kho không? / <ENTITY> có không?
    m2 = re.search(
        r"^(?:thiết\s*bị\s+)?(.*?)\s+(?:có\s+(?:trong\s+kho|ở\s+kho)?\s+không|có\s+không)\??$",
        clean,
        re.IGNORECASE,
    )
    if m2 and m2.group(1).strip():
        cand = m2.group(1).strip()
        cand = re.sub(r"^(?:cái|con|bộ)\s+", "", cand, flags=re.IGNORECASE).strip()
        if cand and cand.lower() not in excluded_cand_terms:
            return True, cand

    return False, None


def parse_dates_vietnamese(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract needed_from and needed_to date strings (YYYY-MM-DD) from Vietnamese natural language.
    
    Examples:
    - 'từ 10/10 đến 12/10'
    - 'từ ngày 10/10/2026 đến 12/10/2026'
    - '10/10 - 12/10'
    - 'từ thứ 2 tuần sau đến cuối tuần sau'
    - 'từ ngày mai đến thứ 6 tuần sau'
    """
    today = date.today()
    current_year = today.year
    dow_map = {
        "2": 0, "hai": 0,
        "3": 1, "ba": 1,
        "4": 2, "tư": 2, "bốn": 2,
        "5": 3, "năm": 3,
        "6": 4, "sáu": 4,
        "7": 5, "bảy": 5,
        "chủ nhật": 6, "cn": 6,
    }

    def _parse_part(d_str: str) -> Optional[date]:
        s = d_str.strip().lower()
        if "hôm nay" in s:
            return today
        if "ngày mai" in s:
            return today + timedelta(days=1)
        if "ngày kia" in s:
            return today + timedelta(days=2)

        # 1. Explicit calendar date: DD/MM/YYYY or DD/MM
        m_dt = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", s)
        if m_dt:
            day = int(m_dt.group(1))
            month = int(m_dt.group(2))
            year = int(m_dt.group(3)) if m_dt.group(3) else current_year
            if year < 100:
                year += 2000
            try:
                return date(year, month, day)
            except ValueError:
                return None

        # 2. Weekday and relative week expressions
        is_next_week = any(w in s for w in ["tuần sau", "tuần tới", "kế tiếp"])
        if any(w in s for w in ["cuối tuần sau", "cuối tuần tới"]):
            # System convention: Sunday of next week
            return today + timedelta(days=13 - today.weekday())
        if "cuối tuần" in s:
            # System convention: Sunday of current week
            return today + timedelta(days=6 - today.weekday())

        m_dow = re.search(r"\b(?:thứ\s*)?(2|3|4|5|6|7|hai|ba|tư|bốn|năm|sáu|bảy|chủ\s*nhật|cn)\b", s)
        if m_dow:
            dow_key = m_dow.group(1).replace(" ", "")
            if dow_key in dow_map:
                target_dow = dow_map[dow_key]
                if is_next_week:
                    next_mon = today + timedelta(days=7 - today.weekday())
                    return next_mon + timedelta(days=target_dow)
                else:
                    this_mon = today - timedelta(days=today.weekday())
                    cand = this_mon + timedelta(days=target_dow)
                    if cand < today:
                        cand += timedelta(days=7)
                    return cand

        return None

    # Pattern 1: từ X đến/tới/- Y
    m_range = re.search(r"từ\s+(.+?)\s+(?:đến|tới|-)\s+([^,.\n]+)", text, re.IGNORECASE)
    if m_range:
        # Avoid capturing trailing project or purpose phrases in d_to
        part_to = m_range.group(2)
        part_to = re.sub(r"(?:cho\s+)?(?:project|dự\s*án).*$", "", part_to, flags=re.IGNORECASE).strip()
        d_from = _parse_part(m_range.group(1))
        d_to = _parse_part(part_to)
        if d_from and d_to:
            if d_to < d_from:
                d_to = d_from
            return (d_from.isoformat(), d_to.isoformat())
        if d_from:
            return (d_from.isoformat(), None)

    # Pattern 2: X - Y (explicit dates)
    m_dash = re.search(r"(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s*[-–]\s*(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)", text)
    if m_dash:
        d_from = _parse_part(m_dash.group(1))
        d_to = _parse_part(m_dash.group(2))
        return (d_from.isoformat() if d_from else None, d_to.isoformat() if d_to else None)

    # Pattern 3: Single date
    m_single = re.search(r"(?:ngày|từ ngày)\s*(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)", text, re.IGNORECASE)
    if m_single:
        d_from = _parse_part(m_single.group(1))
        return (d_from.isoformat() if d_from else None, None)

    return (None, None)


def normalize_return_condition(text: str) -> Optional[str]:
    """Normalize user natural language into one of the 6 official ReturnCondition values:
    - 'Nguyên trạng như khi nhận'
    - 'Có hao mòn nhẹ, vẫn sử dụng bình thường'
    - 'Hư hỏng nhẹ'
    - 'Hư hỏng nặng'
    - 'Hư hỏng nhưng đã khắc phục'
    - 'Cần kiểm tra thêm'
    Returns None if no condition mentioned.
    """
    t = text.lower()

    if any(k in t for k in [
        "hư hỏng nhưng đã khắc phục", "đã khắc phục", "sửa xong", "đã sửa", "hỏng đã sửa", "đã fix"
    ]):
        return "Hư hỏng nhưng đã khắc phục"

    if any(k in t for k in [
        "hư hỏng nặng", "hỏng nặng", "bị vỡ", "gãy", "cháy", "hỏng hoàn toàn", "không lên nguồn"
    ]):
        return "Hư hỏng nặng"

    if any(k in t for k in [
        "hư hỏng nhẹ", "hỏng nhẹ", "lỗi nhẹ", "chập chờn", "hư nhẹ"
    ]):
        return "Hư hỏng nhẹ"

    if any(k in t for k in [
        "hao mòn nhẹ", "mòn nhẹ", "trầy xước nhẹ", "trầy nhẹ", "xước nhẹ", "hơi trầy", "hơi xước", "hao mòn"
    ]):
        return "Có hao mòn nhẹ, vẫn sử dụng bình thường"

    if any(k in t for k in [
        "cần kiểm tra thêm", "cần kiểm tra", "chưa rõ", "chưa kiểm tra", "nghi ngờ lỗi", "không chắc"
    ]):
        return "Cần kiểm tra thêm"

    if any(k in t for k in [
        "nguyên vẹn", "nguyên trạng", "còn nguyên", "không hư hỏng", "không bị hỏng",
        "hoạt động tốt", "dùng tốt", "bình thường", "như ban đầu", "như lúc nhận",
        "mới nguyên"
    ]) or re.search(r"\btốt\b", t):
        return "Nguyên trạng như khi nhận"

    return None


def extract_condition_notes(text: str) -> Optional[str]:
    """Extract equipment condition notes from return requests.
    Example: 'thiết bị còn hoạt động tốt và không bị trầy xước'
    """
    m = re.search(
        r"(?:(?:thiết\s*bị|máy|đồ)?\s*còn\s+[^,.\n]+|hoạt\s*động\s+[^,.\n]+|tình\s*trạng\s*[^,.\n]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        c = m.group(0).strip()
        # Clean leading words if captured
        clean = re.sub(r"^(?:mình|tôi|em)?\s*(?:muốn|cần)?\s*trả\s*(?:thiết\s*bị\s*)?(?:đơn\s*(?:số|#)?\s*\d+\s*)?[,:-]?\s*", "", c, flags=re.IGNORECASE).strip()
        if len(clean) >= 4 and any(w in clean.lower() for w in ["tốt", "bình thường", "trầy", "xước", "hỏng", "mới", "hoạt động", "nguyên"]):
            return clean
    return None


def extract_borrow_fields(text: str) -> dict:
    """Extract potential request fields from user message:
    quantity, dates, project, purpose, condition_notes.
    """
    fields: dict = {}
    
    # 1. Dates
    d_from, d_to = parse_dates_vietnamese(text)
    if d_from:
        fields["needed_from"] = d_from
    if d_to:
        fields["needed_to"] = d_to

    # 2. Condition notes and condition normalization (for return flow)
    cond = extract_condition_notes(text)
    if cond:
        fields["condition_notes"] = cond
    ret_cond = normalize_return_condition(text)
    if ret_cond:
        fields["return_condition"] = ret_cond

    # 3. Clean string for quantity extraction: strip dates, project, condition, IDs, and ordinals
    text_clean = text
    if d_from and d_to:
        text_clean = re.sub(r"từ\s+.*?đến\s+[^,.\n]+", "", text_clean, flags=re.IGNORECASE)
    text_clean = re.sub(r"(?:cho\s+)?(?:project|dự\s*án)\s+[A-Za-z0-9_\-\.]+", "", text_clean, flags=re.IGNORECASE)
    if cond:
        text_clean = text_clean.replace(cond, "")
    text_no_ids = EQUIPMENT_ID_PATTERN.sub("", text_clean)
    text_no_dates = re.sub(r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?", "", text_no_ids)

    # Strip ordinals first so "cái thứ 1" or "đơn thứ 2" is not mistaken for a quantity
    text_no_ordinals = re.sub(r"(?:cái|thiết\s*bị|đơn|item|sản\s*phẩm)?\s*(?:thứ|số)\s*\d+", "", text_no_dates, flags=re.IGNORECASE)
    text_no_ordinals = re.sub(r"\b(thứ\s*(?:nhất|hai|ba|tư|năm)|đầu\s*tiên|cái\s*đầu)\b", "", text_no_ordinals, flags=re.IGNORECASE)
    
    # Match quantity patterns: "cả 2 cái", "cả 2", "mượn 3 cái", "trả 2 cái", "đổi thành 1 cái"
    m_qty_all = re.search(r"\bcả\s*(\d+)\s*(?:cái|chiếc|bộ|con|pcs)?\b", text_no_ordinals, re.IGNORECASE)
    m_qty_explicit = re.search(r"(?:mượn|cần|lấy|trả|hoàn\s*trả|số\s*lượng|đổi\s*thành)\s*(\d+)", text_no_ordinals, re.IGNORECASE)
    if m_qty_all:
        fields["quantity"] = int(m_qty_all.group(1))
    elif m_qty_explicit:
        fields["quantity"] = int(m_qty_explicit.group(1))
    else:
        m_qty_unit = re.search(r"\b(\d+)\s*(?:cái|chiếc|bộ|con|pcs)\b", text_no_ordinals, re.IGNORECASE)
        if m_qty_unit:
            fields["quantity"] = int(m_qty_unit.group(1))

    # 4. Project: "cho project ABC", "dự án ABC", "project ABC"
    m_proj = re.search(r"(?:cho\s+)?(?:project|dự\s*án)\s+([A-Za-z0-9_\-\.]+)", text, re.IGNORECASE)
    if m_proj:
        fields["project"] = m_proj.group(1).strip()

    # 5. Purpose: "để test board", "mục đích là test", "để làm..."
    m_purp = re.search(r"(?:để|mục\s*đích\s*(?:là)?)\s+([^,\.\n]+)", text, re.IGNORECASE)
    if m_purp:
        purp_str = m_purp.group(1).strip()
        purp_str = re.sub(r"(?:cho\s+)?(?:project|dự\s*án)\s+[A-Za-z0-9_\-\.]+", "", purp_str, flags=re.IGNORECASE).strip()
        if purp_str:
            fields["purpose"] = purp_str

    return fields


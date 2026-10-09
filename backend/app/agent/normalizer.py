"""Vietnamese message normalizer and entity pattern extractor."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Optional, Tuple


# Regex patterns for equipment IDs like TU1-001, EBS-030, CSW-001, DEMO-EQ-001
EQUIPMENT_ID_PATTERN = re.compile(
    r"\b(TU1|EBS|CSW|DEMO-EQ)[ _-]?([0-9]{2,4})\b",
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
        "xung đột", "trùng lịch", "lịch"
    ]):
        return False, None

    # Pattern 1: Kho có <ENTITY> không? / Có <ENTITY> không?
    m1 = re.search(
        r"^(?:cho\s+(?:mình|em|tôi)\s+(?:hỏi|biết)\s+)?(?:kiểm\s*tra\s+(?:xem\s+)?)?(?:trong\s+)?(?:kho\s+)?(?:có|còn)\s+(?:thiết\s*bị\s+)?(.*?)(?:\s+(?:không|ko|ạ|nhỉ|\?)\s*)*\??$",
        clean,
        re.IGNORECASE,
    )
    if m1 and m1.group(1).strip():
        cand = m1.group(1).strip()
        cand = re.sub(r"^(?:cái|con|bộ)\s+", "", cand, flags=re.IGNORECASE).strip()
        if cand and cand.lower() not in ["gì", "những gì", "sao", "thế nào"]:
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
        if cand and cand.lower() not in ["gì", "những gì", "sao", "thế nào"]:
            return True, cand

    return False, None


def parse_dates_vietnamese(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract needed_from and needed_to date strings (YYYY-MM-DD) from Vietnamese natural language.
    
    Examples:
    - 'từ 10/10 đến 12/10'
    - 'từ ngày 10/10/2026 đến 12/10/2026'
    - '10/10 - 12/10'
    - 'từ ngày mai đến thứ 6'
    """
    today = date.today()
    current_year = today.year
    
    def _parse_part(d_str: str) -> Optional[date]:
        d_str = d_str.strip()
        if "hôm nay" in d_str.lower():
            return today
        if "ngày mai" in d_str.lower():
            return today + timedelta(days=1)
        if "ngày kia" in d_str.lower():
            return today + timedelta(days=2)
            
        m = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", d_str)
        if m:
            day = int(m.group(1))
            month = int(m.group(2))
            year = int(m.group(3)) if m.group(3) else current_year
            if year < 100:
                year += 2000
            try:
                return date(year, month, day)
            except ValueError:
                return None
        return None

    # Pattern: từ X đến Y
    m_range = re.search(r"từ\s+([^đến\-]+)\s+(?:đến|tới|-)\s+([^,\.\n]+)", text, re.IGNORECASE)
    if m_range:
        d_from = _parse_part(m_range.group(1))
        d_to = _parse_part(m_range.group(2))
        return (d_from.isoformat() if d_from else None, d_to.isoformat() if d_to else None)

    # Pattern: X - Y (where both look like dates)
    m_dash = re.search(r"(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s*[-–]\s*(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)", text)
    if m_dash:
        d_from = _parse_part(m_dash.group(1))
        d_to = _parse_part(m_dash.group(2))
        return (d_from.isoformat() if d_from else None, d_to.isoformat() if d_to else None)

    # Single date
    m_single = re.search(r"(?:ngày|từ ngày)\s*(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)", text, re.IGNORECASE)
    if m_single:
        d_from = _parse_part(m_single.group(1))
        return (d_from.isoformat() if d_from else None, None)

    return (None, None)


def extract_borrow_fields(text: str) -> dict:
    """Extract potential request fields from user message:
    quantity, dates, project, purpose.
    """
    fields: dict = {}
    
    # 1. Dates
    d_from, d_to = parse_dates_vietnamese(text)
    if d_from:
        fields["needed_from"] = d_from
    if d_to:
        fields["needed_to"] = d_to

    # 2. Quantity
    # Look for "5 cái", "số lượng 5", "5 chiếc", "mượn 5", or standalone number near beginning
    m_qty = re.search(r"\b(\d+)\s*(?:cái|chiếc|bộ|con|pcs|item)?\b", text, re.IGNORECASE)
    # Be careful not to match date numbers or equipment numbers (e.g. TU1-001)
    # Remove dates and equipment IDs before checking quantity
    text_no_ids = EQUIPMENT_ID_PATTERN.sub("", text)
    text_no_dates = re.sub(r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?", "", text_no_ids)
    
    # Match quantity patterns
    m_qty_explicit = re.search(r"(?:mượn|cần|lấy|số\s*lượng)\s*(\d+)", text_no_dates, re.IGNORECASE)
    if m_qty_explicit:
        fields["quantity"] = int(m_qty_explicit.group(1))
    else:
        # Check for standalone count like "5 cái"
        m_qty_unit = re.search(r"\b(\d+)\s*(?:cái|chiếc|bộ|con|pcs)\b", text_no_dates, re.IGNORECASE)
        if m_qty_unit:
            fields["quantity"] = int(m_qty_unit.group(1))

    # 3. Project: "cho project ABC", "dự án ABC", "project ABC"
    m_proj = re.search(r"(?:cho\s+)?(?:project|dự\s*án)\s+([A-Za-z0-9_\-\.]+)", text, re.IGNORECASE)
    if m_proj:
        fields["project"] = m_proj.group(1).strip()

    # 4. Purpose: "để test board", "mục đích là test", "để làm..."
    m_purp = re.search(r"(?:để|mục\s*đích\s*(?:là)?)\s+([^,\.\n]+)", text, re.IGNORECASE)
    if m_purp:
        # Avoid including project if captured together
        purp_str = m_proj_stripped = m_purp.group(1).strip()
        purp_str = re.sub(r"(?:cho\s+)?(?:project|dự\s*án)\s+[A-Za-z0-9_\-\.]+", "", purp_str, flags=re.IGNORECASE).strip()
        if purp_str:
            fields["purpose"] = purp_str

    return fields

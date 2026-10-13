"""Schedule conflict service - calculates deterministic conflict pairs."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Sequence

from app.schemas.requests import RequestStatus

# Statuses that participate in schedule conflicts
CONFLICT_STATUSES = {
    RequestStatus.PENDING.value,
    RequestStatus.APPROVED.value,
    RequestStatus.BORROWED.value,
}


def parse_date(d: Any) -> date | None:
    """Parse string or date to date object."""
    if not d:
        return None
    if isinstance(d, date):
        return d
    try:
        s = str(d).strip()[:10]
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def dates_overlap(start_a: date | None, end_a: date | None, start_b: date | None, end_b: date | None) -> bool:
    """Return True if two date intervals overlap: start_a <= end_b and start_b <= end_a."""
    if not start_a or not end_a or not start_b or not end_b:
        return False
    return start_a <= end_b and start_b <= end_a


def calculate_overlap_duration(start_a: date, end_a: date, start_b: date, end_b: date) -> tuple[int, str, str, str]:
    """Calculate overlap duration in days and formatted string."""
    o_start = max(start_a, start_b)
    o_end = min(end_a, end_b)
    overlap_days = max(1, (o_end - o_start).days + 1)

    start_str = o_start.strftime("%d/%m/%Y")
    end_str = o_end.strftime("%d/%m/%Y")
    if o_start == o_end:
        duration_str = f"1 ngày ({start_str})"
    else:
        duration_str = f"{overlap_days} ngày ({start_str} - {end_str})"

    return overlap_days, duration_str, str(o_start), str(o_end)


def format_date_vn(d: Any) -> str:
    """Format string or date object to Vietnamese DD/MM/YYYY string."""
    parsed = parse_date(d)
    if parsed:
        return parsed.strftime("%d/%m/%Y")
    return str(d) if d else ""


class ConflictService:
    """Deterministic schedule conflict calculation service."""

    def find_conflict_pairs(
        self,
        requests: Sequence[Any],
        equipment_map: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Identify unique conflicting request pairs.

        Rules:
        - Must reference the same EquipmentID
        - Must be distinct requests (id != other.id)
        - Both must be in CONFLICT_STATUSES (Pending, Approved, Borrowed)
        - Must have overlapping date intervals
        - Each unordered pair (A, B) appears exactly once
        - Canonical pair key: min(id_A, id_B) + '_' + max(id_A, id_B)
        - Duplicate content signatures are deduplicated to prevent artificial inflation
        """
        eq_map = equipment_map or {}

        # Filter active requests with valid equipment and dates
        active = []
        for r in requests:
            st = getattr(r, "status", None)
            if st not in CONFLICT_STATUSES:
                continue
            eq_id = getattr(r, "equipment_id", None)
            if not eq_id:
                continue
            s_date = parse_date(getattr(r, "needed_from", None))
            e_date = parse_date(getattr(r, "needed_to", None))
            if not s_date or not e_date or s_date > e_date:
                continue
            active.append((r, eq_id, s_date, e_date))

        # Group by equipment_id to avoid O(N^2) across different equipment
        by_equipment: dict[str, list[tuple[Any, str, date, date]]] = {}
        for item in active:
            by_equipment.setdefault(item[1], []).append(item)

        pairs: list[dict[str, Any]] = []
        seen_pair_keys: set[str] = set()
        seen_content_pairs: set[tuple[tuple, tuple]] = set()

        for eq_id, eq_items in by_equipment.items():
            n = len(eq_items)
            for i in range(n):
                r_a, _, start_a, end_a = eq_items[i]
                id_a = getattr(r_a, "id", None)
                if id_a is None:
                    continue

                for j in range(i + 1, n):
                    r_b, _, start_b, end_b = eq_items[j]
                    id_b = getattr(r_b, "id", None)
                    if id_b is None or id_a == id_b:
                        continue

                    # Date overlap check
                    if not dates_overlap(start_a, end_a, start_b, end_b):
                        continue

                    # Canonical pair key by ID
                    min_id = min(id_a, id_b)
                    max_id = max(id_a, id_b)
                    pair_key = f"{min_id}_{max_id}"
                    if pair_key in seen_pair_keys:
                        continue

                    # Content signature check to avoid duplicate seed rows inflating counts
                    sig_a = (
                        eq_id,
                        str(start_a),
                        str(end_a),
                        getattr(r_a, "requester_email", "") or getattr(r_a, "requester_name", ""),
                        getattr(r_a, "project", ""),
                        getattr(r_a, "status", ""),
                    )
                    sig_b = (
                        eq_id,
                        str(start_b),
                        str(end_b),
                        getattr(r_b, "requester_email", "") or getattr(r_b, "requester_name", ""),
                        getattr(r_b, "project", ""),
                        getattr(r_b, "status", ""),
                    )
                    # Duplicate seed records of the same request should not conflict with each other
                    if sig_a == sig_b:
                        continue

                    content_pair_sig = tuple(sorted([sig_a, sig_b]))
                    if content_pair_sig in seen_content_pairs:
                        continue

                    seen_pair_keys.add(pair_key)
                    seen_content_pairs.add(content_pair_sig)

                    # Calculate overlap duration
                    overlap_days, overlap_str, o_from, o_to = calculate_overlap_duration(
                        start_a, end_a, start_b, end_b
                    )

                    # Standardize request A and B: put Pending request as A if one is Pending and one is Approved/Borrowed,
                    # otherwise order canonically by min_id
                    if getattr(r_b, "status", "") == "Pending" and getattr(r_a, "status", "") != "Pending":
                        first_r, second_r = r_b, r_a
                        f_start, f_end = start_b, end_b
                        s_start, s_end = start_a, end_a
                    else:
                        first_r, second_r = r_a, r_b
                        f_start, f_end = start_a, end_a
                        s_start, s_end = start_b, end_b

                    first_id_str = getattr(first_r, "request_id", None) or getattr(first_r, "display_id", f"REQ-{first_r.id:06d}")
                    second_id_str = getattr(second_r, "request_id", None) or getattr(second_r, "display_id", f"REQ-{second_r.id:06d}")
                    eq_name = eq_map.get(eq_id) or getattr(first_r, "equipment_name", None) or getattr(second_r, "equipment_name", None) or eq_id

                    record = {
                        "pair_key": pair_key,
                        "equipment_id": eq_id,
                        "equipment_name": eq_name,

                        # Request A
                        "request_id_a": first_id_str,
                        "id_a": first_r.id,
                        "requester_name_a": getattr(first_r, "requester_name", ""),
                        "requester_email_a": getattr(first_r, "requester_email", "") or "",
                        "project_a": getattr(first_r, "project", ""),
                        "needed_from_a": str(f_start),
                        "needed_to_a": str(f_end),
                        "needed_from_a_vn": format_date_vn(f_start),
                        "needed_to_a_vn": format_date_vn(f_end),
                        "status_a": getattr(first_r, "status", ""),
                        "quantity_a": getattr(first_r, "quantity", 1),
                        "priority_level_a": getattr(first_r, "final_priority_level", None) or getattr(first_r, "priority_level", "Medium"),
                        "purpose_a": getattr(first_r, "purpose", ""),

                        # Request B
                        "request_id_b": second_id_str,
                        "id_b": second_r.id,
                        "requester_name_b": getattr(second_r, "requester_name", ""),
                        "requester_email_b": getattr(second_r, "requester_email", "") or "",
                        "project_b": getattr(second_r, "project", ""),
                        "needed_from_b": str(s_start),
                        "needed_to_b": str(s_end),
                        "needed_from_b_vn": format_date_vn(s_start),
                        "needed_to_b_vn": format_date_vn(s_end),
                        "status_b": getattr(second_r, "status", ""),
                        "quantity_b": getattr(second_r, "quantity", 1),
                        "priority_level_b": getattr(second_r, "final_priority_level", None) or getattr(second_r, "priority_level", "Medium"),
                        "purpose_b": getattr(second_r, "purpose", ""),

                        # Overlap details
                        "overlap_days": overlap_days,
                        "overlap_duration": overlap_str,
                        "overlap_from": o_from,
                        "overlap_to": o_to,

                        # Backward compatibility aliases
                        "request_id": first_id_str,
                        "id": first_r.id,
                        "requester_name": getattr(first_r, "requester_name", ""),
                        "requester_email": getattr(first_r, "requester_email", "") or "",
                        "project": getattr(first_r, "project", ""),
                        "needed_from": str(f_start),
                        "needed_to": str(f_end),
                        "status": getattr(first_r, "status", ""),
                        "quantity": getattr(first_r, "quantity", 1),
                        "priority_level": getattr(first_r, "final_priority_level", None) or getattr(first_r, "priority_level", "Medium"),
                        "purpose": getattr(first_r, "purpose", ""),
                        "conflicting_with_id": second_id_str,
                        "conflicting_requester_name": getattr(second_r, "requester_name", ""),
                        "conflicting_project": getattr(second_r, "project", ""),
                        "conflicting_needed_from": str(s_start),
                        "conflicting_needed_to": str(s_end),
                        "conflicting_status": getattr(second_r, "status", ""),
                        "conflicting_quantity": getattr(second_r, "quantity", 1),
                        "conflicting_priority_level": getattr(second_r, "final_priority_level", None) or getattr(second_r, "priority_level", "Medium"),
                        "conflicting_purpose": getattr(second_r, "purpose", ""),

                        # Object references for backward compatibility with agent tool inspection
                        "pending_request": first_r,
                        "conflicting_requests": [second_r],
                    }
                    pairs.append(record)

        return pairs

    def count_conflict_pairs(
        self,
        requests: Sequence[Any],
        equipment_map: dict[str, str] | None = None,
    ) -> int:
        """Count unique conflicting request pairs."""
        return len(self.find_conflict_pairs(requests, equipment_map))

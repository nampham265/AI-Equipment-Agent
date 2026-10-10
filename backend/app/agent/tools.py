"""Role-aware, deterministic tool registry for Agent Orchestration."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from app.agent.models import ExtractedConstraints
from app.agent.retrieval import HybridRetrievalService
from app.core.config import settings
from app.repositories.base import EquipmentRepository, RequestRepository, UserRepository
from app.schemas.equipment import EquipmentRead
from app.schemas.requests import RequestCreate, RequestRead
from app.agent.services.external_sourcing import ExternalSourcingService
from app.services.approval_service import ApprovalService
from app.services.availability_service import AvailabilityService
from app.services.priority_service import PriorityService


def classify_equipment_role(name: str, desc: str = "", category: str = "") -> str:
    """Classify equipment into a functional role:
    SENSOR, HOLDER, CONNECTOR, CABLE, CONTROLLER, MATERIAL, TOOL, UNVERIFIED.
    """
    text = f"{name} {desc} {category}".lower()
    if any(k in text for k in ["holder", "giá đỡ", "khung/giá đỡ", "bracket", "mount", "gá", "chân đế"]):
        return "HOLDER"
    if any(k in text for k in ["connector", "đầu nối", "giắc", "jack", "terminal", "housing", "plug", "cụm đầu nối"]):
        return "CONNECTOR"
    if any(k in text for k in ["cable", "cáp", "dây nối", "wire", "jumper", "harness", "dây"]):
        return "CABLE"
    if any(k in text for k in ["sensor", "cảm biến", "wss", "wheelspeed", "hall", "encoder", "áp suất"]):
        return "SENSOR"
    if any(k in text for k in ["ecu", "controller", "bộ điều khiển", "vi điều khiển", "module", "can"]):
        return "CONTROLLER"
    if any(k in text for k in ["pla", "filament", "nhựa in", "vật tư", "băng dính"]):
        return "MATERIAL"
    if any(k in text for k in ["kìm", "tô vít", "absorber", "hút khói", "mỏ hàn", "dụng cụ"]):
        return "TOOL"
    return "UNVERIFIED"


class AgentTools:
    """Deterministic backend services exposed as typed tools to the Agent."""

    def __init__(
        self,
        equipment_repo: EquipmentRepository,
        request_repo: RequestRepository,
        user_repo: Optional[UserRepository] = None,
        priority_service: Optional[PriorityService] = None,
        availability_service: Optional[AvailabilityService] = None,
        approval_service: Optional[ApprovalService] = None,
        external_sourcing_service: Optional[ExternalSourcingService] = None,
    ) -> None:
        self.equipment_repo = equipment_repo
        self.request_repo = request_repo
        self.user_repo = user_repo
        self.retrieval = HybridRetrievalService(equipment_repo)
        self.priority_service = priority_service
        self.availability_service = availability_service or AvailabilityService(request_repo)
        if not approval_service:
            from app.notifications.console_provider import ConsoleNotificationProvider
            from app.services.notification_service import NotificationService
            approval_service = ApprovalService(request_repo, NotificationService(ConsoleNotificationProvider()))
        self.approval_service = approval_service
        self.external_sourcing_svc = external_sourcing_service or ExternalSourcingService()

    # -------------------------------------------------------------
    # User Tools
    # -------------------------------------------------------------

    def search_equipment(
        self,
        constraints: ExtractedConstraints,
        query: Optional[str] = None,
        exact_id: Optional[str] = None,
    ) -> list[EquipmentRead]:
        """Search equipment matching constraints."""
        return self.retrieval.search_equipment(constraints, query, exact_id)

    def get_equipment_detail(self, equipment_id: str) -> Optional[EquipmentRead]:
        """Get full details of a specific equipment."""
        return self.equipment_repo.get_by_id(equipment_id.strip().upper())

    def get_low_stock_inventory(
        self,
        threshold: Optional[int] = None,
        operator: str = "<=",
    ) -> dict[str, Any]:
        """Retrieve equipment records with recorded stock quantity meeting low-stock threshold.

        Args:
            threshold: Positive integer threshold. Defaults to settings.LOW_STOCK_THRESHOLD if None.
            operator: Comparison operator ('<' or '<='). Defaults to '<='.

        Returns:
            dict with threshold, operator, total_matches, and items list.
        """
        configured_default = getattr(settings, "LOW_STOCK_THRESHOLD", 5)
        if threshold is None or not isinstance(threshold, int) or threshold <= 0:
            effective_threshold = configured_default
        else:
            effective_threshold = threshold

        effective_operator = operator if operator in ["<", "<="] else "<="

        all_eq = self.equipment_repo.get_all()
        matching_items: list[dict[str, Any]] = []

        for eq in all_eq:
            raw_qty = None
            if hasattr(eq, "quantity_total"):
                val = getattr(eq, "quantity_total")
                if val is not None:
                    raw_qty = val
            if raw_qty is None and hasattr(eq, "quantity"):
                val = getattr(eq, "quantity")
                if val is not None:
                    raw_qty = val

            if raw_qty is None:
                continue

            # Ensure valid numeric value
            if isinstance(raw_qty, (int, float)):
                qty_val = int(raw_qty)
            elif isinstance(raw_qty, str) and raw_qty.strip().lstrip("-").isdigit():
                try:
                    qty_val = int(raw_qty.strip())
                except ValueError:
                    continue
            else:
                continue

            if effective_operator == "<":
                is_match = (qty_val < effective_threshold)
            else:
                is_match = (qty_val <= effective_threshold)

            if is_match:
                matching_items.append({
                    "equipment_id": eq.equipment_id,
                    "equipment_name": eq.equipment_name,
                    "recorded_quantity": qty_val,
                    "unit": eq.unit or "cái",
                    "location": eq.location or "Chưa xác định",
                    "category": eq.category or "Chưa phân loại",
                })

        # Deterministic sort: ascending by recorded_quantity, then tie-break by equipment_id
        matching_items.sort(key=lambda x: (x["recorded_quantity"], str(x["equipment_id"])))

        return {
            "threshold": effective_threshold,
            "operator": effective_operator,
            "total_matches": len(matching_items),
            "items": matching_items,
        }

    def get_out_of_stock_inventory(self) -> dict[str, Any]:
        """Retrieve equipment records with recorded stock quantity == 0 (strictly out of stock).

        Returns:
            dict with condition, total_matches, and items list sorted deterministically.
        """
        all_eq = self.equipment_repo.get_all()
        matching_items: list[dict[str, Any]] = []

        for eq in all_eq:
            raw_qty = None
            if hasattr(eq, "quantity_total"):
                val = getattr(eq, "quantity_total")
                if val is not None:
                    raw_qty = val
            if raw_qty is None and hasattr(eq, "quantity"):
                val = getattr(eq, "quantity")
                if val is not None:
                    raw_qty = val

            if raw_qty is None:
                continue

            # Ensure valid numeric value
            if isinstance(raw_qty, (int, float)):
                qty_val = int(raw_qty)
            elif isinstance(raw_qty, str) and raw_qty.strip().lstrip("-").isdigit():
                try:
                    qty_val = int(raw_qty.strip())
                except ValueError:
                    continue
            else:
                continue

            # Out of stock strictly means Quantity == 0
            if qty_val == 0:
                matching_items.append({
                    "equipment_id": eq.equipment_id,
                    "equipment_name": eq.equipment_name,
                    "recorded_quantity": 0,
                    "unit": eq.unit or "cái",
                    "location": eq.location or "Chưa xác định",
                    "category": eq.category or "Chưa phân loại",
                })

        # Deterministic sort: tie-break by equipment_id
        matching_items.sort(key=lambda x: str(x["equipment_id"]))

        return {
            "condition": "Quantity == 0",
            "total_matches": len(matching_items),
            "items": matching_items,
        }

    def get_equipment_count(self, equipment_id: str) -> dict[str, Any]:
        """Get deterministic quantity information for an equipment, with inventory inconsistency detection."""
        eq = self.equipment_repo.get_by_id(equipment_id.strip().upper())
        if not eq:
            return {"found": False, "equipment_id": equipment_id}
        
        # Check active loans
        overlapping = self.request_repo.get_overlapping(
            equipment_id=eq.equipment_id,
            needed_from="2000-01-01",
            needed_to="2099-12-31",
            statuses=["Approved", "Borrowed"],
        )
        borrowed_qty = sum(r.quantity for r in overlapping if r.status == "Borrowed")
        approved_qty = sum(r.quantity for r in overlapping if r.status == "Approved")
        has_inconsistency = borrowed_qty > eq.quantity_total
        inconsistency_note = (
            f"⚠️ Cảnh báo bất thường dữ liệu: Số lượng ghi nhận đang mượn ({borrowed_qty}) "
            f"vượt quá tổng tồn kho ({eq.quantity_total}). Cần thủ kho đối soát lại chứng từ mượn/trả."
            if has_inconsistency else None
        )
        available_now = max(0, eq.quantity_total - (borrowed_qty + approved_qty))

        return {
            "found": True,
            "equipment_id": eq.equipment_id,
            "equipment_name": eq.equipment_name,
            "quantity_total": eq.quantity_total,
            "unit": eq.unit or "cái",
            "location": eq.location or "Chưa rõ",
            "borrowed_quantity": borrowed_qty,
            "approved_quantity": approved_qty,
            "available_quantity": available_now,
            "has_inconsistency": has_inconsistency,
            "inconsistency_note": inconsistency_note,
        }

    def check_availability(
        self,
        equipment_id: str,
        needed_from: str,
        needed_to: str,
    ) -> dict[str, Any]:
        """Check availability in a specific date range."""
        eq = self.equipment_repo.get_by_id(equipment_id)
        qty_total = eq.quantity_total if eq else 0
        avail = self.availability_service.calculate(
            equipment_id=equipment_id,
            needed_from=needed_from,
            needed_to=needed_to,
            quantity_total=qty_total,
        )
        return avail.model_dump()

    def create_request(
        self,
        requester_name: str,
        requester_email: str,
        project: str,
        equipment_id: str,
        quantity: int,
        needed_from: str,
        needed_to: str,
        purpose: str,
    ) -> RequestRead:
        """Create a new borrow request with automated priority assessment."""
        eq = self.equipment_repo.get_by_id(equipment_id)
        if not eq:
            raise ValueError(f"Thiết bị '{equipment_id}' không tồn tại trong kho.")

        # Determine priority via priority service
        prio_level = "Needs review"
        prio_reason = "Chờ quản lý xem xét"
        if self.priority_service:
            assessment = self.priority_service.assess(
                equipment=eq,
                quantity=quantity,
                needed_from=needed_from,
                needed_to=needed_to,
                purpose=purpose,
                project=project,
                requester_name=requester_name,
            )
            prio_level = assessment.priority_level
            prio_reason = assessment.priority_reason

        req_model = RequestRead(
            id=0,
            requester_name=requester_name,
            requester_email=requester_email,
            project=project,
            equipment_id=equipment_id,
            equipment_name=eq.equipment_name,
            quantity=quantity,
            needed_from=needed_from,
            needed_to=needed_to,
            purpose=purpose,
            priority_level=prio_level,
            priority_reason=prio_reason,
            status="Pending",
            created_at=datetime.now(timezone.utc).isoformat(),
            modified_at=datetime.now(timezone.utc).isoformat(),
        )
        return self.request_repo.create(req_model)

    def list_my_requests(self, user_email: str, status: Optional[str] = None) -> list[RequestRead]:
        """List requests submitted by current user, optionally filtered by status."""
        reqs = self.request_repo.list_by_requester(user_email)
        if status:
            reqs = [r for r in reqs if (r.status or "").lower() == status.lower()]
        return reqs

    def get_equipment_active_loans(self, equipment_id: str) -> list[RequestRead]:
        """List current approved or borrowed requests for equipment (to answer project usage)."""
        return self.request_repo.get_overlapping(
            equipment_id=equipment_id.strip().upper(),
            needed_from="2000-01-01",
            needed_to="2099-12-31",
            statuses=["Approved", "Borrowed"],
        )

    def get_active_loans_for_user(self, user_email: str) -> list[RequestRead]:
        """Get all currently-borrowed requests for a specific user (for return flow)."""
        all_borrowed = self.request_repo.list_all(status="Borrowed")
        return [
            r for r in all_borrowed
            if (r.requester_email or "").strip().lower() == user_email.strip().lower()
        ]

    def submit_user_return(
        self,
        request_id: int,
        user_email: str,
        return_condition: str,
        return_condition_note: str = "",
    ) -> RequestRead:
        """Submit a return for a specific borrowed request (user-initiated)."""
        return self.approval_service.mark_returned(
            request_id=request_id,
            return_condition=return_condition,
            return_condition_note=return_condition_note or None,
            actor_email=user_email,
        )

    # -------------------------------------------------------------
    # Manager Tools (Role Gated)
    # -------------------------------------------------------------

    def count_pending_requests(self, manager_email: str) -> dict[str, int]:
        """Get actionable pending requests count for manager."""
        all_pending = self.request_repo.list_all(status="Pending")
        total_pending = len(all_pending)
        actionable = [r for r in all_pending if (r.requester_email or "").lower() != manager_email.lower()]
        self_pending = [r for r in all_pending if (r.requester_email or "").lower() == manager_email.lower()]

        return {
            "total_pending": total_pending,
            "actionable_pending": len(actionable),
            "self_pending": len(self_pending),
        }

    def list_pending_requests(self, manager_email: Optional[str] = None) -> list[RequestRead]:
        """List pending requests."""
        return self.request_repo.list_all(status="Pending")

    def get_recent_requests(self, limit: int = 5) -> list[RequestRead]:
        """List most recently created requests sorted by created_at DESC."""
        all_reqs = self.request_repo.list_all()
        all_reqs.sort(key=lambda r: (r.created_at or "", r.id), reverse=True)
        return all_reqs[:limit]

    def get_most_recent_request(self) -> Optional[RequestRead]:
        """Get the single most recently created request."""
        recent = self.get_recent_requests(limit=1)
        return recent[0] if recent else None

    def get_overdue_loans(self, ref_date: Optional[date] = None) -> list[dict[str, Any]]:
        """Get list of borrowed equipment that is past the needed_to return date."""
        today = ref_date or date.today()
        all_reqs = self.request_repo.list_all(status="Borrowed")
        overdue_items = []
        for r in all_reqs:
            if not r.needed_to:
                continue
            try:
                due_d = datetime.strptime(r.needed_to[:10], "%Y-%m-%d").date()
                if today > due_d:
                    days_overdue = (today - due_d).days
                    req_id_str = getattr(r, "request_id", None) or getattr(r, "display_id", None) or f"REQ-{r.id:06d}"
                    overdue_items.append({
                        "RequestID": req_id_str,
                        "id": r.id,
                        "RequesterName": r.requester_name,
                        "RequesterEmail": getattr(r, "requester_email", "") or "",
                        "EquipmentID": r.equipment_id,
                        "EquipmentName": r.equipment_name,
                        "Project": r.project,
                        "NeededFrom": r.needed_from,
                        "NeededTo": r.needed_to,
                        "Status": r.status,
                        "Quantity": r.quantity,
                        "Purpose": r.purpose,
                        "PriorityLevel": r.priority_level,
                        "days_overdue": days_overdue,
                        "overdue_days": days_overdue,
                        "borrower": r.requester_name,
                        "borrower_email": getattr(r, "requester_email", "") or "",
                        "equipment_name": r.equipment_name,
                        "equipment_id": r.equipment_id,
                        "project": r.project,
                        "needed_from": r.needed_from,
                        "needed_to": r.needed_to,
                        "status": r.status,
                        "quantity": r.quantity,
                    })
            except Exception:
                continue
        overdue_items.sort(key=lambda x: x["days_overdue"], reverse=True)
        return overdue_items

    def get_active_loans(self) -> list[RequestRead]:
        """List active loans (Status == 'Borrowed' only)."""
        return self.request_repo.list_all(status="Borrowed")

    def get_active_borrowers(self) -> list[dict[str, Any]]:
        """Aggregate active borrowers based on Borrowed requests."""
        borrowed = self.request_repo.list_all(status="Borrowed")
        grouped: dict[str, dict[str, Any]] = {}
        for r in borrowed:
            key = (r.requester_email or r.requester_name).strip().lower()
            if key not in grouped:
                grouped[key] = {
                    "name": r.requester_name,
                    "email": r.requester_email,
                    "total_quantity": 0,
                    "request_count": 0,
                    "equipment_items": [],
                }
            grouped[key]["total_quantity"] += r.quantity
            grouped[key]["request_count"] += 1
            grouped[key]["equipment_items"].append({
                "id": r.id,
                "equipment_id": r.equipment_id,
                "equipment_name": r.equipment_name,
                "quantity": r.quantity,
                "project": r.project,
                "needed_to": r.needed_to,
            })
        return list(grouped.values())

    def get_schedule_conflicts(self) -> list[dict[str, Any]]:
        """Find pending requests that overlap with existing approved/borrowed requests."""
        pending = self.request_repo.list_all(status="Pending")
        conflicts = []
        for p in pending:
            overlapping = self.request_repo.get_overlapping(
                equipment_id=p.equipment_id,
                needed_from=p.needed_from,
                needed_to=p.needed_to,
                statuses=["Approved", "Borrowed"],
                exclude_id=p.id,
            )
            if overlapping:
                conflicts.append({
                    "pending_request": p,
                    "conflicting_requests": overlapping,
                })
        return conflicts

    def get_request_detail(self, request_id: int) -> Optional[RequestRead]:
        """Get detail of a specific request."""
        return self.request_repo.get_by_id(request_id)

    def review_priority(
        self,
        request_id: int,
        new_priority: str,
        reviewer_name: str,
        reviewer_email: str,
    ) -> RequestRead:
        """Manager adjusts priority level of a request."""
        valid_levels = ["Critical", "High", "Medium", "Low", "Needs review"]
        if new_priority not in valid_levels:
            raise ValueError(f"Mức ưu tiên không hợp lệ: {new_priority}. Cho phép: {valid_levels}")

        req = self.request_repo.get_by_id(request_id)
        if not req:
            raise ValueError(f"Không tìm thấy yêu cầu #{request_id}")

        req.final_priority_level = new_priority
        req.priority_reviewed_by = reviewer_email
        req.priority_reviewed_at = datetime.now(timezone.utc).isoformat()
        req.modified_at = datetime.now(timezone.utc).isoformat()
        return self.request_repo.update(req)

    def approve_request(
        self,
        request_id: int,
        manager_email: str,
        manager_name: str,
    ) -> RequestRead:
        """Manager approves request. Strictly enforces self-approval prevention."""
        req = self.request_repo.get_by_id(request_id)
        if not req:
            raise ValueError(f"Không tìm thấy yêu cầu #{request_id}")

        # Guard: self-approval prevention
        if (req.requester_email or "").strip().lower() == manager_email.strip().lower():
            raise PermissionError("Quản lý không thể tự phê duyệt yêu cầu mượn của chính mình.")

        return self.approval_service.approve(request_id, manager_name)

    def reject_request(
        self,
        request_id: int,
        manager_name: str,
        manager_email: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> RequestRead:
        """Manager rejects request."""
        req = self.request_repo.get_by_id(request_id)
        if not req:
            raise ValueError(f"Không tìm thấy yêu cầu #{request_id}")

        if manager_email and (req.requester_email or "").strip().lower() == manager_email.strip().lower():
            raise PermissionError("Quản lý không thể tự xử lý hoặc từ chối yêu cầu mượn của chính mình.")

        return self.approval_service.reject(request_id, manager_name, reason or "")

    # -------------------------------------------------------------
    # Admin Tools (Role Gated)
    # -------------------------------------------------------------

    def list_users(self) -> list[Any]:
        """List all users in the system."""
        if not self.user_repo:
            return []
        return self.user_repo.list_all()

    def create_user(self, email: str, name: str, role: str) -> Any:
        """Admin creates a new user."""
        if not self.user_repo:
            raise RuntimeError("User repository not configured.")
        from app.schemas.users import UserCreate
        return self.user_repo.create_user(UserCreate(user_email=email, user_name=name, role=role))

    def update_user_role(self, email: str, new_role: str, admin_email: str) -> Any:
        """Admin changes a user's role."""
        if not self.user_repo:
            raise RuntimeError("User repository not configured.")
        return self.user_repo.update_role(email, new_role, admin_email)

    # -------------------------------------------------------------
    # Missing Capabilities Tools (Phase 2)
    # -------------------------------------------------------------

    def search_alternative_equipment(
        self,
        target_equipment_id: Optional[str] = None,
        target_equipment_name: Optional[str] = None,
        constraints: Optional[ExtractedConstraints] = None,
        max_results: int = 5,
        limit: Optional[int] = None,
    ) -> dict[str, Any]:
        """Find alternative/substitute equipment.
        Target equipment is NEVER included in results.
        Strictly differentiates description similarity from technical compatibility,
        and distinguishes functional devices from mechanical accessories (holders/connectors).
        """
        import re
        effective_limit = limit if limit is not None else max_results
        target_id_clean = (target_equipment_id or "").strip().upper()
        target_obj = self.equipment_repo.get_by_id(target_id_clean) if target_id_clean else None

        category = target_obj.category if target_obj and target_obj.category else (constraints.category if constraints else None)
        all_equipment = self.equipment_repo.get_all()
        candidates = []

        target_name_str = target_obj.equipment_name if target_obj else (target_equipment_name or "")
        target_desc_str = target_obj.description if target_obj and target_obj.description else ""
        target_role = classify_equipment_role(target_name_str, target_desc_str, category or "")

        target_is_wss = any(k in f"{target_name_str} {target_desc_str}".lower() for k in ["wheelspeed", "wss", "tốc độ bánh xe", "tốc độ vòng quay", "wheel speed"])

        for eq in all_equipment:
            # CRITICAL RULE: Target equipment MUST NEVER appear in its own alternative results
            if target_id_clean and eq.equipment_id.upper() == target_id_clean:
                continue
            if target_equipment_name and eq.equipment_name.strip().lower() == target_equipment_name.strip().lower():
                continue

            eq_name = eq.equipment_name or ""
            eq_desc = eq.description or ""
            cand_role = classify_equipment_role(eq_name, eq_desc, eq.category or "")
            cand_is_wss = any(k in f"{eq_name} {eq_desc}".lower() for k in ["wheelspeed", "wss", "tốc độ bánh xe", "tốc độ vòng quay", "wheel speed"])

            matched_specs: list[str] = []
            unverified_specs: list[str] = []
            compatibility_status: str = "UNVERIFIED"
            suitability_label: str = "Chưa xác minh"
            technical_note: str = ""
            is_interchangeable: bool = False

            # Evaluate technical compatibility
            if target_role == "SENSOR":
                if cand_role in ["HOLDER", "CONNECTOR", "CABLE"]:
                    compatibility_status = "ACCESSORY_NOT_SUBSTITUTE"
                    role_vn = "giá đỡ/gá lắp cơ khí" if cand_role == "HOLDER" else ("đầu nối/giắc cắm" if cand_role == "CONNECTOR" else "dây cáp")
                    suitability_label = "ACCESSORY_NOT_SUBSTITUTE"
                    display_label = "Phụ kiện đi kèm — Không thể thay thế cảm biến"
                    technical_note = f"Đây là {role_vn}, không có chức năng đo lường/cảm biến của thiết bị gốc."
                    unverified_specs.append(f"Không có chức năng cảm biến ({role_vn})")
                elif cand_role == "SENSOR":
                    if target_is_wss and cand_is_wss:
                        compatibility_status = "POTENTIALLY_SUITABLE"
                        suitability_label = "POTENTIALLY_SUITABLE"
                        display_label = "Có thể phù hợp (cần kiểm tra thêm datasheet)"
                        technical_note = "Cùng chức năng cảm biến tốc độ bánh xe (WSS). Cần đối soát datasheet về air-gap, điện áp hoạt động và dạng xung tín hiệu."
                        is_interchangeable = True
                        matched_specs.append("Cùng chức năng đo tốc độ bánh xe (Wheel Speed Sensor)")
                        unverified_specs.extend([
                            "Khoảng cách đọc air-gap",
                            "Điện áp hoạt động (Operating Voltage)",
                            "Dạng xung tín hiệu (Signal Protocol/Output)",
                        ])
                    else:
                        compatibility_status = "UNVERIFIED"
                        suitability_label = "SAME_CATEGORY"
                        display_label = "Chưa xác minh (Khác phân loại cảm biến)"
                        technical_note = "Cùng phân loại cảm biến nhưng đo lường đại lượng khác nhau hoặc khác mục đích kỹ thuật. Không tương thích."
                        unverified_specs.append("Khác đại lượng đo lường / thông số kỹ thuật")
                else:
                    compatibility_status = "INCOMPATIBLE"
                    suitability_label = "DIFFERENT_FORM_FACTOR"
                    display_label = "Không tương thích"
                    technical_note = "Khác nhóm chức năng kỹ thuật."
            else:
                if cand_role == target_role and target_role != "UNVERIFIED":
                    compatibility_status = "POTENTIALLY_SUITABLE"
                    suitability_label = "POTENTIALLY_SUITABLE"
                    display_label = "Có thể phù hợp (cùng nhóm chức năng)"
                    technical_note = f"Cùng nhóm thiết bị {target_role}. Cần kiểm tra thông số chi tiết."
                    is_interchangeable = True
                else:
                    compatibility_status = "UNVERIFIED"
                    suitability_label = "SAME_CATEGORY" if (category and (eq.category or "").lower() == category.lower()) else "DIFFERENT_FORM_FACTOR"
                    display_label = "Chưa xác minh"
                    technical_note = "Khác nhóm thiết bị hoặc chưa đủ dữ liệu kỹ thuật đối soát."

            # Calculate grounded text similarity score (0 - 100)
            score = 0
            if category and (eq.category or "").lower() == category.lower():
                score += 15
                matched_specs.append(f"Cùng nhóm: {eq.category}")

            if target_obj and target_obj.description and eq.description:
                target_words = set(re.findall(r"\w+", target_obj.description.lower()))
                eq_words = set(re.findall(r"\w+", eq.description.lower()))
                stop_words = {"và", "với", "cho", "loại", "cái", "mm", "khoảng", "tủ", "các", "khi", "để", "được", "có", "trên", "từ", "về"}
                common = (target_words & eq_words) - stop_words
                common_count = len(common)
                if common_count >= 1:
                    score += min(common_count * 5, 30)

            if is_interchangeable:
                score += 35  # Major boost for functional role match
            elif compatibility_status == "ACCESSORY_NOT_SUBSTITUTE":
                score = min(score, 35)  # Cap accessory score so it never claims high equivalence
            elif compatibility_status == "INCOMPATIBLE":
                score = min(score, 15)

            # Only include relevant items (same category or related keywords or functional relevance)
            if score >= 15 or cand_is_wss or (category and (eq.category or "").lower() == category.lower()):
                candidates.append({
                    "equipment": eq,
                    "score": min(score, 100),
                    "compatibility_status": compatibility_status,
                    "suitability_label": suitability_label,
                    "display_label": display_label,
                    "technical_note": technical_note,
                    "matched_specs": matched_specs,
                    "unverified_specs": unverified_specs,
                    "is_interchangeable": is_interchangeable,
                })

        # Deterministic sorting: interchangeable items FIRST, then descending by score, tie-break equipment_id
        candidates.sort(key=lambda x: (1 if x["is_interchangeable"] else 0, x["score"], str(x["equipment"].equipment_id)), reverse=True)
        top_candidates = candidates[:effective_limit]

        return {
            "success": True,
            "target_equipment_id": target_id_clean,
            "target_equipment_name": target_obj.equipment_name if target_obj else target_equipment_name,
            "target_name": target_obj.equipment_name if target_obj else (target_equipment_name or target_id_clean),
            "target_role": target_role,
            "has_official_equivalence": False,
            "official_equivalence_notice": "Kho hiện chưa có danh mục quy chuẩn tương đương chính thức 1-1. Đề xuất dưới đây dựa trên phân loại chức năng kỹ thuật và đối soát thuộc tính.",
            "alternatives": [
                {
                    "equipment": c["equipment"],
                    "suitability_label": c["suitability_label"],
                    "display_label": c.get("display_label") or c["suitability_label"],
                    "compatibility_status": c["compatibility_status"],
                    "score": c["score"],
                    "technical_note": c["technical_note"],
                    "matched_specs": c["matched_specs"],
                    "unverified_specs": c["unverified_specs"],
                    "is_interchangeable": c["is_interchangeable"],
                }
                for c in top_candidates
            ],
            "candidates": top_candidates,
        }


    def external_sourcing_search(
        self,
        product_query: str,
        constraints: Optional[dict[str, Any]] = None,
        max_results: int = 3,
    ) -> dict[str, Any]:
        """Search external suppliers/sources outside warehouse inventory."""
        if not self.external_sourcing_svc:
            self.external_sourcing_svc = ExternalSourcingService()
        res = self.external_sourcing_svc.search_sources(product_query, constraints, max_results)
        return res.model_dump()

    def get_equipment_project_usage(self, equipment_id: str) -> dict[str, Any]:
        """Query active project usage for an equipment. ONLY 'Borrowed' requests count as active usage."""
        eq = self.equipment_repo.get_by_id(equipment_id.strip().upper())
        all_borrowed = self.request_repo.list_all(status="Borrowed")
        matching_loans = [
            r for r in all_borrowed
            if r.equipment_id.strip().upper() == equipment_id.strip().upper()
        ]

        return {
            "equipment_id": equipment_id.strip().upper(),
            "equipment_name": eq.equipment_name if eq else equipment_id,
            "is_borrowed": len(matching_loans) > 0,
            "active_loans_count": len(matching_loans),
            "usage_records": [
                {
                    "request_id": getattr(r, "display_id", f"REQ-{r.id:06d}"),
                    "project": r.project,
                    "requester": r.requester_name,
                    "quantity": r.quantity,
                    "needed_from": r.needed_from,
                    "needed_to": r.needed_to,
                    "status": r.status,
                }
                for r in matching_loans
            ],
        }

    def equipment_availability_schedule(self, equipment_id: str, quantity_needed: int = 1) -> dict[str, Any]:
        """Estimate release dates based on NeededTo of currently Borrowed requests."""
        usage_info = self.get_equipment_project_usage(equipment_id)
        if not usage_info["is_borrowed"]:
            return {
                "equipment_id": equipment_id,
                "status": "AVAILABLE_NOW",
                "message": "Thiết bị hiện không có đơn mượn nào đang giữ (trạng thái Borrowed). Các dự án khác có thể đăng ký mượn ngay.",
                "earliest_release_date": None,
                "borrowed_records": [],
            }

        records = sorted(usage_info["usage_records"], key=lambda r: r.get("needed_to") or "9999-12-31")
        earliest_return = records[0].get("needed_to")
        proj_name = records[0].get("project") or "hiện tại"

        return {
            "equipment_id": equipment_id,
            "status": "CURRENTLY_BORROWED",
            "message": f"Dựa trên các phiếu mượn thực tế đang giữ đồ, dự án {proj_name} dự kiến trả vào ngày {earliest_return}.",
            "earliest_release_date": earliest_return,
            "borrowed_records": records,
        }

    def add_user_account(
        self,
        user_email: str,
        user_name: str,
        role: str,
        actor_role: str,
    ) -> dict[str, Any]:
        """Add a new user/manager. Strictly protected by RBAC (ADMIN only, cannot create ADMIN)."""
        if (actor_role or "").upper() != "ADMIN":
            raise PermissionError("Chỉ người dùng có quyền ADMIN mới được phép tạo tài khoản người dùng mới.")

        target_role = role.strip().upper()
        if target_role not in ["USER", "MANAGER"]:
            raise ValueError(f"Vai trò không hợp lệ: '{role}'. Chỉ cho phép tạo vai trò USER hoặc MANAGER qua luồng này.")

        email_clean = user_email.strip().lower()
        if not email_clean or "@" not in email_clean:
            raise ValueError(f"Email không hợp lệ: '{user_email}'")

        if not self.user_repo:
            raise RuntimeError("Hệ thống quản trị tài khoản người dùng chưa được cấu hình.")

        existing = self.user_repo.get_by_email(email_clean)
        if existing:
            raise ValueError(f"Người dùng với email '{email_clean}' đã tồn tại trong hệ thống.")

        from app.schemas.users import UserCreate
        created = self.user_repo.create_user(UserCreate(
            user_email=email_clean,
            user_name=user_name.strip() or email_clean.split("@")[0].title(),
            role=target_role,
        ))
        return {
            "success": True,
            "user_email": created.user_email,
            "user_name": created.user_name,
            "role": created.role,
            "is_active": created.is_active,
        }

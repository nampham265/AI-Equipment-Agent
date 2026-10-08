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
from app.services.approval_service import ApprovalService
from app.services.availability_service import AvailabilityService
from app.services.priority_service import PriorityService


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
    ) -> None:
        self.equipment_repo = equipment_repo
        self.request_repo = request_repo
        self.user_repo = user_repo
        self.retrieval = HybridRetrievalService(equipment_repo)
        self.priority_service = priority_service
        self.availability_service = availability_service or AvailabilityService(request_repo)
        self.approval_service = approval_service or ApprovalService(request_repo)

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

    def get_equipment_count(self, equipment_id: str) -> dict[str, Any]:
        """Get deterministic quantity information for an equipment."""
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

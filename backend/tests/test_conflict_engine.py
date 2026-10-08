"""Comprehensive unit and regression tests for the Schedule Conflict Engine."""
from __future__ import annotations

from types import SimpleNamespace
import pytest
from app.services.conflict_service import ConflictService, dates_overlap, parse_date


def _req(
    id: int,
    equipment_id: str,
    needed_from: str,
    needed_to: str,
    status: str = "Pending",
    requester_name: str = "Test User",
    requester_email: str = "test@company.com",
    project: str = "Project X",
    equipment_name: str = "Demo Equipment",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        display_id=f"REQ-{id:06d}",
        request_id=f"REQ-{id:06d}",
        equipment_id=equipment_id,
        equipment_name=equipment_name,
        needed_from=needed_from,
        needed_to=needed_to,
        status=status,
        requester_name=requester_name,
        requester_email=requester_email,
        project=project,
    )


class TestConflictServiceCore:
    def test_self_comparison_is_excluded(self):
        """A request compared with itself must NEVER produce a conflict."""
        svc = ConflictService()
        req_a = _req(1, "TU1-002", "2026-11-01", "2026-11-05")
        pairs = svc.find_conflict_pairs([req_a])
        assert len(pairs) == 0
        assert svc.count_conflict_pairs([req_a]) == 0

    def test_canonical_pair_uniqueness_and_order_independence(self):
        """Pair A-B appears exactly once; B-A does not appear separately."""
        svc = ConflictService()
        req_a = _req(1, "TU1-002", "2026-11-01", "2026-11-05", status="Pending")
        req_b = _req(2, "TU1-002", "2026-11-03", "2026-11-07", status="Approved")

        # Order [A, B]
        pairs_ab = svc.find_conflict_pairs([req_a, req_b])
        assert len(pairs_ab) == 1
        assert pairs_ab[0]["pair_key"] == "1_2"

        # Reversed order [B, A]
        pairs_ba = svc.find_conflict_pairs([req_b, req_a])
        assert len(pairs_ba) == 1
        assert pairs_ba[0]["pair_key"] == "1_2"

    def test_deterministic_conflict_fixtures(self):
        """Specification fixture verification:
        A: TU1-002 01/11–05/11
        B: TU1-002 03/11–07/11 -> exactly 1 conflict pair A-B
        C: TU1-002 08/11–10/11 -> no conflict with A or B
        D: TU1-008 03/11–07/11 -> no conflict because EquipmentID differs
        Expected:
        A-B = 1
        A-C = 0
        A-D = 0
        """
        svc = ConflictService()
        req_a = _req(1, "TU1-002", "2026-11-01", "2026-11-05", status="Pending")
        req_b = _req(2, "TU1-002", "2026-11-03", "2026-11-07", status="Approved")
        req_c = _req(3, "TU1-002", "2026-11-08", "2026-11-10", status="Pending")
        req_d = _req(4, "TU1-008", "2026-11-03", "2026-11-07", status="Pending")

        pairs = svc.find_conflict_pairs([req_a, req_b, req_c, req_d])

        # Exactly 1 pair total
        assert len(pairs) == 1
        p = pairs[0]
        assert p["equipment_id"] == "TU1-002"
        pair_ids = {p["id_a"], p["id_b"]}
        assert pair_ids == {1, 2}

        # Verify C and D do not participate in any pairs
        all_participating_ids = {pid for p in pairs for pid in (p["id_a"], p["id_b"])}
        assert 3 not in all_participating_ids
        assert 4 not in all_participating_ids

    def test_different_equipment_does_not_conflict(self):
        """Requests with identical dates but different EquipmentIDs must not conflict."""
        svc = ConflictService()
        req_1 = _req(1, "TU1-001", "2026-11-01", "2026-11-05")
        req_2 = _req(2, "TU1-002", "2026-11-01", "2026-11-05")
        assert len(svc.find_conflict_pairs([req_1, req_2])) == 0

    def test_adjacent_non_overlapping_dates_do_not_conflict(self):
        """Dates that do not overlap (e.g. 01/11-05/11 and 06/11-10/11) must not conflict."""
        svc = ConflictService()
        req_1 = _req(1, "TU1-002", "2026-11-01", "2026-11-05")
        req_2 = _req(2, "TU1-002", "2026-11-06", "2026-11-10")
        assert len(svc.find_conflict_pairs([req_1, req_2])) == 0

    def test_overlap_duration_calculation(self):
        """Overlap interval and duration string must be computed accurately."""
        svc = ConflictService()
        req_a = _req(1, "TU1-002", "2026-11-01", "2026-11-05")
        req_b = _req(2, "TU1-002", "2026-11-03", "2026-11-07")

        pairs = svc.find_conflict_pairs([req_a, req_b])
        assert len(pairs) == 1
        p = pairs[0]
        assert p["overlap_days"] == 3  # 03/11, 04/11, 05/11 inclusive
        assert p["overlap_from"] == "2026-11-03"
        assert p["overlap_to"] == "2026-11-05"
        assert "3 ngày" in p["overlap_duration"]
        assert "03/11/2026 - 05/11/2026" in p["overlap_duration"]

    def test_inactive_statuses_excluded(self):
        """Cancelled, Rejected, Returned requests must NOT participate in conflicts."""
        svc = ConflictService()
        req_active = _req(1, "TU1-002", "2026-11-01", "2026-11-05", status="Pending")
        req_cancelled = _req(2, "TU1-002", "2026-11-01", "2026-11-05", status="Cancelled")
        req_rejected = _req(3, "TU1-002", "2026-11-01", "2026-11-05", status="Rejected")
        req_returned = _req(4, "TU1-002", "2026-11-01", "2026-11-05", status="Returned")

        pairs = svc.find_conflict_pairs([req_active, req_cancelled, req_rejected, req_returned])
        assert len(pairs) == 0

    def test_duplicate_seed_records_do_not_multiply_pairs(self):
        """10 duplicate copies of request A and 10 duplicate copies of request B
        must yield exactly 1 logical conflict pair, not 100 pairs."""
        svc = ConflictService()
        requests = []
        for i in range(10):
            requests.append(_req(100 + i, "TU1-002", "2026-11-01", "2026-11-05", status="Pending"))
        for j in range(10):
            requests.append(_req(200 + j, "TU1-002", "2026-11-03", "2026-11-07", status="Approved"))

        pairs = svc.find_conflict_pairs(requests)
        assert len(pairs) == 1


class TestConflictAPIIntegration:
    def test_kpi_count_equals_detail_count(self):
        """Dashboard KPI conflicts_count MUST equal length of /api/manager/conflicts."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        res_login = client.post("/auth/dev-login", json={"email": "nampham.31231023820@st.ueh.edu.vn"})
        assert res_login.status_code == 200

        res_summary = client.get("/api/manager/summary")
        assert res_summary.status_code == 200
        summary_count = res_summary.json()["conflicts_count"]

        res_conflicts = client.get("/api/manager/conflicts")
        assert res_conflicts.status_code == 200
        detail_list = res_conflicts.json()

        assert summary_count == len(detail_list), (
            f"KPI count ({summary_count}) does NOT equal detail count ({len(detail_list)})!"
        )

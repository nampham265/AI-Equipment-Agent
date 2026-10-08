"""Hybrid multi-constraint retrieval service for Equipment Inventory."""
from __future__ import annotations

import re
from typing import Any, Optional

from app.agent.models import ExtractedConstraints
from app.repositories.base import EquipmentRepository
from app.schemas.equipment import EquipmentRead


class HybridRetrievalService:
    """Multi-constraint deterministic inventory search engine."""

    def __init__(self, equipment_repo: EquipmentRepository) -> None:
        self.equipment_repo = equipment_repo

    def search_equipment(
        self,
        constraints: ExtractedConstraints,
        query_text: Optional[str] = None,
        exact_id: Optional[str] = None,
    ) -> list[EquipmentRead]:
        """Perform multi-constraint structured retrieval over the inventory."""
        # 1. Exact ID match has highest priority
        if exact_id:
            eq = self.equipment_repo.get_by_id(exact_id.strip().upper())
            if eq:
                return [eq]

        all_items = self.equipment_repo.list_all()

        # If general catalog browsing (no constraints or keywords), preserve natural order
        is_general = not (
            constraints.location
            or constraints.category
            or constraints.geometry
            or constraints.size_mm
            or constraints.pins
            or constraints.color
            or constraints.gender
            or constraints.keywords
        )
        if is_general:
            return all_items

        scored_candidates: list[tuple[float, EquipmentRead]] = []

        for item in all_items:
            # Check hard constraints
            if not self._matches_constraints(item, constraints):
                continue

            # Calculate score
            score = self._calculate_score(item, constraints, query_text)
            # Relevance threshold: must have positive score >= 15.0 when filtering
            if score >= 15.0:
                scored_candidates.append((score, item))

        # Sort: score descending, then equipment_id ascending
        scored_candidates.sort(key=lambda x: (-x[0], x[1].equipment_id))
        return [item for _, item in scored_candidates]

    def _matches_constraints(self, item: EquipmentRead, c: ExtractedConstraints) -> bool:
        """Verify hard filters: location, geometry, size_mm, pins, category, color, gender."""
        full_text = f"{item.equipment_id} {item.equipment_name} {item.description or ''} {item.location or ''}".lower()

        # Location filter
        if c.location:
            item_loc = (item.location or "").lower()
            target_loc = c.location.lower()
            if target_loc in ["tủ 1", "tu 1"]:
                if "tủ 1" not in item_loc and "tu 1" not in item_loc and "tu1" not in item.equipment_id.lower():
                    return False
            elif target_loc in ["csw", "tủ csw"]:
                if "csw" not in item_loc and "csw" not in item.equipment_id.lower():
                    return False
            elif target_loc in ["ebs", "ebs_lab", "lab"]:
                if "ebs" not in item_loc and "ebs" not in item.equipment_id.lower():
                    return False
            elif target_loc not in item_loc:
                return False

        # Category filter
        if c.category:
            item_cat = (item.category or "").lower()
            item_desc = (item.description or "").lower()
            item_name = (item.equipment_name or "").lower()
            target_cat = c.category.lower()
            if (
                target_cat not in item_cat
                and target_cat not in item_name
                and target_cat not in item_desc
            ):
                return False

        # Geometry filter (e.g. R/A / right-angle vs SMD)
        if c.geometry:
            target_geom = c.geometry.lower()
            if target_geom == "r/a":
                # Must contain r/a, right-angle, right angle, or góc vuông
                if not any(g in full_text for g in ["r/a", "right-angle", "right angle", "góc vuông"]):
                    return False
            elif target_geom == "smd":
                if "smd" not in full_text:
                    return False

        # Size mm filter (e.g. 4.2mm, 3mm)
        if c.size_mm is not None:
            size_str = str(c.size_mm)
            if size_str.endswith(".0"):
                size_simple = size_str[:-2]
            else:
                size_simple = size_str
            pattern = rf"\b{re.escape(size_simple)}(?:\.0)?\s*(?:mm|ly)?\b"
            if not re.search(pattern, full_text):
                return False

        # Pins filter (e.g. 10pos, 6pos, 8pos)
        if c.pins is not None:
            p_val = c.pins
            pattern = rf"\b{p_val}\s*(?:pos|pin|chân)\b"
            if not re.search(pattern, full_text):
                return False

        # Color filter (e.g. đen, trắng, vàng, tím, black, white)
        if c.color:
            col = c.color.lower()
            if col in ["đen", "black"]:
                if not any(k in full_text for k in ["đen", "black"]):
                    return False
            elif col in ["trắng", "white"]:
                if not any(k in full_text for k in ["trắng", "white"]):
                    return False
            elif col in ["vàng", "yellow"]:
                if not any(k in full_text for k in ["vàng", "yellow"]):
                    return False
            elif col in ["tím", "purple"]:
                if not any(k in full_text for k in ["tím", "purple"]):
                    return False
            elif col not in full_text:
                return False

        # Gender filter (e.g. female / cái vs male / đực)
        if c.gender:
            gen = c.gender.lower()
            if gen in ["female", "cái"]:
                if not any(k in full_text for k in ["female", "loại cái", "ổ cái", "đầu cái"]):
                    return False
            elif gen in ["male", "đực"]:
                if not any(k in full_text for k in ["male", "loại đực", "lõi đực", "đầu đực"]):
                    return False

        # If user specified specific search keywords, candidate MUST match distinctive keywords
        if c.keywords:
            if "interface" in c.keywords and "interface" not in full_text:
                return False
            if "banana" in c.keywords and "banana" not in full_text:
                return False
            matched_kw_count = sum(1 for kw in c.keywords if kw in full_text)
            if matched_kw_count == 0:
                return False

        return True

    def _calculate_score(
        self,
        item: EquipmentRead,
        c: ExtractedConstraints,
        query_text: Optional[str],
    ) -> float:
        """Calculate lexical and constraint relevance score."""
        score = 15.0  # Base score for passing hard filters

        full_text = f"{item.equipment_id} {item.equipment_name} {item.description or ''} {item.location or ''}".lower()

        # Bonus for keywords
        if c.keywords:
            matched_kws = [kw for kw in c.keywords if kw in full_text]
            score += len(matched_kws) * 15.0
            # Extra bonus if ALL keywords match
            if len(matched_kws) == len(c.keywords) and len(c.keywords) > 1:
                score += 40.0
            # Phrase bonus (e.g. "interface board" or "banana jumper")
            phrase = " ".join(c.keywords)
            if phrase in full_text:
                score += 50.0

        if query_text:
            q_clean = query_text.lower().strip()
            # Normalize punctuation for comparison
            q_norm = re.sub(r"[\s\-_.,/()]+", "", q_clean)
            id_norm = re.sub(r"[\s\-_.,/()]+", "", item.equipment_id.lower())
            name_norm = re.sub(r"[\s\-_.,/()]+", "", item.equipment_name.lower())

            if id_norm and id_norm == q_norm:
                score += 150.0
            elif id_norm and id_norm in q_norm:
                score += 100.0
            elif id_norm and q_norm in id_norm and len(q_norm) >= 3:
                score += 80.0

            if name_norm and name_norm == q_norm:
                score += 120.0
            elif name_norm and (name_norm in q_norm or q_norm in name_norm) and len(q_norm) >= 3:
                score += 70.0
            elif q_clean in item.equipment_name.lower():
                score += 50.0

        return score

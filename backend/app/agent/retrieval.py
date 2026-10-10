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

        # Determine whether this is a general warehouse catalog browsing request
        is_general = False
        if query_text:
            q_clean = query_text.strip().lower()
            general_phrases = [
                "những món gì", "những thiết bị gì", "các món gì", "các thiết bị gì",
                "loại thiết bị nào", "danh sách thiết bị", "kho đang có gì", "trong kho có gì",
                "kho hiện có gì", "tất cả thiết bị", "toàn bộ thiết bị", "kho có gì",
            ]
            is_general = any(p in q_clean for p in general_phrases) and not any(
                w in q_clean for w in [
                    "connector", "cable", "abs", "sensor", "board", "cáp", "cảm biến",
                    "mạch", "dây", "công tắc", "switch", "relay", "rơ le", "caninterface",
                    "jumper", "header", "rcpt", "hsg", "lemo", "orico", "hub", "cos"
                ]
            )
        elif not (
            constraints.location
            or constraints.category
            or constraints.geometry
            or constraints.size_mm
            or constraints.pins
            or constraints.color
            or constraints.gender
            or constraints.keywords
        ):
            is_general = True

        if is_general:
            return all_items

        # Build effective constraints from query_text tokens if keywords are empty
        effective_constraints = constraints
        if query_text and not constraints.keywords:
            stop_words = {
                "mình", "tôi", "em", "muốn", "cần", "tìm", "xem", "cho", "xin",
                "trong", "kho", "có", "không", "những", "các", "cái", "chiếc", "cục",
                "bộ", "món", "hiện", "tại", "đang", "được", "là", "gì", "ở", "nào",
                "để", "thì", "với", "và", "ạ", "nhỉ", "hỏi", "biết"
            }
            tokens = [
                w for w in re.findall(r"[A-Za-z0-9_\-\./]+", query_text.lower())
                if w not in stop_words and len(w) >= 2
            ]
            if tokens:
                effective_constraints = ExtractedConstraints(
                    category=constraints.category,
                    location=constraints.location,
                    geometry=constraints.geometry,
                    size_mm=constraints.size_mm,
                    pins=constraints.pins,
                    color=constraints.color,
                    gender=constraints.gender,
                    keywords=tokens,
                )

        scored_candidates: list[tuple[float, EquipmentRead]] = []

        for item in all_items:
            # Check hard constraints
            if not self._matches_constraints(item, effective_constraints):
                continue

            # Calculate score
            score = self._calculate_score(item, effective_constraints, query_text)
            # Relevance threshold: must have positive score >= 15.0 when filtering
            if score >= 15.0:
                scored_candidates.append((score, item))

        # Sort: score descending, then equipment_id ascending
        scored_candidates.sort(key=lambda x: (-x[0], x[1].equipment_id))
        return [item for _, item in scored_candidates]

    def _matches_constraints(self, item: EquipmentRead, c: ExtractedConstraints) -> bool:
        """Verify hard filters: location, geometry, size_mm, pins, category, color, gender."""
        full_text = f"{item.equipment_id} {item.equipment_name} {item.category or ''} {item.description or ''} {item.location or ''}".lower()

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
            target_cats = [tc.strip().lower() for tc in c.category.split("/") if tc.strip()]
            if not any(
                tc in item_cat or tc in item_name or tc in item_desc
                for tc in target_cats
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
            elif col in ["đỏ", "red"]:
                if not any(k in full_text for k in ["đỏ", "red"]):
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
            c_kws_lower = [k.lower() for k in c.keywords]
            primary_text = f"{item.equipment_id} {item.equipment_name} {item.category or ''}".lower()

            if "interface" in c_kws_lower and not re.search(r"\binterface\b", full_text):
                return False
            if "banana" in c_kws_lower and not re.search(r"\bbanana\b", full_text):
                return False

            # Specific rule for ABS: must be in primary_text (ECU ABS, Connector ABS), not incidental description mention
            if "abs" in c_kws_lower and not re.search(r"\babs\b", primary_text):
                return False

            # If searching for banana jumper, must match banana in primary_text
            if "banana" in c_kws_lower and "jumper" in c_kws_lower and not re.search(r"\bbanana\b", primary_text):
                return False

            matched_kw_count = 0
            for kw in c_kws_lower:
                if re.search(rf"\b{re.escape(kw)}\b", full_text):
                    matched_kw_count += 1
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

        full_text = f"{item.equipment_id} {item.equipment_name} {item.category or ''} {item.description or ''} {item.location or ''}".lower()
        primary_text = f"{item.equipment_id} {item.equipment_name} {item.category or ''}".lower()
        desc_text = (item.description or "").lower()

        # Bonus for keywords matching primary text vs description
        if c.keywords:
            c_kws_lower = [k.lower() for k in c.keywords]
            matched_primary = [kw for kw in c_kws_lower if re.search(rf"\b{re.escape(kw)}\b", primary_text)]
            matched_desc = [kw for kw in c_kws_lower if re.search(rf"\b{re.escape(kw)}\b", desc_text)]

            score += len(matched_primary) * 35.0 + len(matched_desc) * 5.0
            # Extra bonus if ALL keywords match in primary text
            if len(matched_primary) == len(c_kws_lower) and len(c_kws_lower) > 0:
                score += 50.0
            # Phrase bonus
            phrase = " ".join(c_kws_lower)
            if phrase in primary_text:
                score += 60.0
            elif phrase in full_text:
                score += 20.0

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

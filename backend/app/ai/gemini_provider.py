"""Gemini AI provider.

Uses google-genai SDK with multi-model fallback and rate-limit resilience.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.ai.base import LLMProvider

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an equipment priority assessment AI for a university lab.
Given an equipment borrow request and context, determine the priority level.

Priority levels (choose exactly one):
- Critical: Essential for safety, time-critical research deadline, or irreplaceable need
- High: Important project milestone, significant impact if delayed
- Medium: Standard request with reasonable timeline
- Low: Convenience or non-urgent, flexible dates
- Needs review: Insufficient information to determine, conflicting data, or edge case

Return a JSON object with EXACTLY these fields (no extra fields):
{
  "priority_level": "<one of the 5 levels above>",
  "priority_reason": "<max 1000 chars, in Vietnamese>",
  "evidence": ["<evidence point 1>", "<evidence point 2>"],
  "needs_manager_review": <true|false>
}

Base your assessment on:
1. The stated purpose and urgency
2. Competition with other requests (Approved/Borrowed = committed conflicts, Pending = competing)
3. Equipment availability vs requested quantity
4. Project importance signals in the purpose text
"""

FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
]


class GeminiAIProvider(LLMProvider):
    """Calls Google Gemini API for structured priority assessment using google-genai."""

    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-lite") -> None:
        self._api_key = api_key
        self._model_name = model

    def assess_priority(
        self,
        request_data: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            logger.error("google-genai not installed; falling back to Needs review")
            return self._fallback("google-genai package không được cài đặt.")

        if not self._api_key:
            return self._fallback("Thiếu API key cho Gemini.")

        prompt = (
            f"Request data:\n{json.dumps(request_data, ensure_ascii=False, indent=2)}\n\n"
            f"Context:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
        )

        config = types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.2,
        )

        # Build candidate models list: primary model first, followed by fallbacks
        models_to_try = [self._model_name]
        for m in FALLBACK_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error = ""
        client = genai.Client(api_key=self._api_key)

        for attempt_idx, model in enumerate(models_to_try):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )

                raw = response.text.strip()
                parsed = json.loads(raw)
                return self._validate(parsed)

            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Gemini model '%s' call failed (attempt %d/%d): %s. Trying fallback model...",
                    model,
                    attempt_idx + 1,
                    len(models_to_try),
                    exc,
                )
                time.sleep(0.5)

        logger.error("All Gemini models failed: %s", last_error)
        return self._fallback(last_error)

    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate and sanitize Gemini output against the expected schema."""
        from app.schemas.requests import PriorityLevel

        valid_levels = {lvl.value for lvl in PriorityLevel}
        level = data.get("priority_level", "")
        if level not in valid_levels:
            logger.warning("Gemini returned invalid priority_level '%s'; forcing Needs review", level)
            level = "Needs review"

        reason = str(data.get("priority_reason", ""))[:1000]
        evidence = [str(e) for e in data.get("evidence", []) if isinstance(e, str)]
        needs_review = bool(data.get("needs_manager_review", False))

        return {
            "priority_level": level,
            "priority_reason": reason,
            "evidence": evidence,
            "needs_manager_review": needs_review,
        }

    def _fallback(self, reason: str) -> dict[str, Any]:
        return {
            "priority_level": "Needs review",
            "priority_reason": (
                f"Đánh giá ưu tiên tự động không thành công. "
                f"Quản lý vui lòng xem xét. (Chi tiết: {reason[:200]})"
            ),
            "evidence": [],
            "needs_manager_review": True,
        }

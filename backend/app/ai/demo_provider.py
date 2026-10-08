"""[DEMO AI PROVIDER] - Does NOT call any external AI service.

Returns 'Needs review' with an honest explanation that no AI is configured.
This is the safe fallback when GEMINI_API_KEY is not set.
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.base import LLMProvider

logger = logging.getLogger(__name__)


class DemoAIProvider(LLMProvider):
    """Demo provider clearly labelled - no real AI inference performed."""

    def assess_priority(
        self,
        request_data: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        logger.info(
            "[DEMO AI PROVIDER] assess_priority called - returning 'Needs review' "
            "because no AI provider is configured."
        )
        return {
            "priority_level": "Needs review",
            "priority_reason": (
                "[DEMO] Hệ thống đang chạy ở chế độ demo, chưa có AI thực được cấu hình. "
                "Quản lý vui lòng xem xét và phân loại ưu tiên thủ công."
            ),
            "evidence": [
                "Không có GEMINI_API_KEY được cấu hình.",
                "AI_PROVIDER đang được đặt thành 'demo'.",
            ],
            "needs_manager_review": True,
        }

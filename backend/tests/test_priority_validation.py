"""Tests for AI priority assessment validation."""
from __future__ import annotations

import pytest

from app.schemas.requests import PriorityAssessment, PriorityLevel
from app.ai.demo_provider import DemoAIProvider
from app.ai.gemini_provider import GeminiAIProvider


class TestDemoProvider:
    def test_returns_needs_review(self):
        provider = DemoAIProvider()
        result = provider.assess_priority({}, {})
        assert result["priority_level"] == "Needs review"
        assert result["needs_manager_review"] is True
        assert len(result["priority_reason"]) > 0
        assert isinstance(result["evidence"], list)

    def test_result_matches_schema(self):
        provider = DemoAIProvider()
        result = provider.assess_priority({}, {})
        # Should be parseable as PriorityAssessment
        assessment = PriorityAssessment(**result)
        assert assessment.priority_level == PriorityLevel.NEEDS_REVIEW


class TestPriorityAssessmentSchema:
    def test_valid_priority_levels(self):
        for level in ("Critical", "High", "Medium", "Low", "Needs review"):
            a = PriorityAssessment(
                priority_level=level,
                priority_reason="Test reason",
                evidence=[],
                needs_manager_review=False,
            )
            assert a.priority_level.value == level

    def test_invalid_priority_level_raises(self):
        with pytest.raises(Exception):
            PriorityAssessment(
                priority_level="VeryUrgent",  # invalid
                priority_reason="Test",
                evidence=[],
                needs_manager_review=False,
            )

    def test_priority_reason_max_length(self):
        long_reason = "x" * 1001  # exceeds 1000 chars
        with pytest.raises(Exception):
            PriorityAssessment(
                priority_level="Medium",
                priority_reason=long_reason,
                evidence=[],
                needs_manager_review=False,
            )

    def test_priority_reason_at_limit(self):
        reason = "x" * 1000  # exactly 1000 chars - valid
        a = PriorityAssessment(
            priority_level="Medium",
            priority_reason=reason,
            evidence=[],
            needs_manager_review=False,
        )
        assert len(a.priority_reason) == 1000

    def test_evidence_defaults_to_empty_list(self):
        a = PriorityAssessment(
            priority_level="Low",
            priority_reason="reason",
        )
        assert a.evidence == []
        assert a.needs_manager_review is False


class TestGeminiProviderValidation:
    """Test the Gemini provider's internal validation logic without calling the API."""

    def _provider(self) -> GeminiAIProvider:
        return GeminiAIProvider(api_key="fake-key", model="gemini-test")

    def test_validate_valid_output(self):
        provider = self._provider()
        data = {
            "priority_level": "High",
            "priority_reason": "Urgent research deadline",
            "evidence": ["Project milestone in 2 days"],
            "needs_manager_review": False,
        }
        result = provider._validate(data)
        assert result["priority_level"] == "High"
        assert result["needs_manager_review"] is False

    def test_validate_invalid_level_becomes_needs_review(self):
        provider = self._provider()
        data = {
            "priority_level": "SUPER_CRITICAL",  # invalid
            "priority_reason": "Some reason",
            "evidence": [],
            "needs_manager_review": False,
        }
        result = provider._validate(data)
        assert result["priority_level"] == "Needs review"

    def test_validate_truncates_long_reason(self):
        provider = self._provider()
        data = {
            "priority_level": "Low",
            "priority_reason": "x" * 2000,  # too long
            "evidence": [],
            "needs_manager_review": False,
        }
        result = provider._validate(data)
        assert len(result["priority_reason"]) == 1000

    def test_fallback_returns_needs_review(self):
        provider = self._provider()
        result = provider._fallback("network error")
        assert result["priority_level"] == "Needs review"
        assert result["needs_manager_review"] is True
        assert "network error" in result["priority_reason"]

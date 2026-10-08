"""AI provider abstract interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Interface that every AI provider must implement."""

    @abstractmethod
    def assess_priority(
        self,
        request_data: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a PriorityAssessment-compatible dict.

        Args:
            request_data: The borrow request being assessed.
            context: Dict with keys:
                - equipment: equipment details dict
                - overlapping_approved_borrowed: list of dicts
                - overlapping_pending: list of dicts
        """
        ...

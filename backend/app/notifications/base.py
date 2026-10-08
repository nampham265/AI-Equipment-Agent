"""Notification provider abstract interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.request import RequestModel


class NotificationProvider(ABC):
    """Port for sending approval / rejection notifications."""

    @abstractmethod
    def send_approval_notification(
        self,
        request: "RequestModel",
        approved: bool,
    ) -> None:
        """Send a notification about approval or rejection of a request."""
        ...

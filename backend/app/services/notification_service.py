"""Notification service - thin wrapper around the notification provider."""
from __future__ import annotations

import logging

from app.models.request import RequestModel
from app.notifications.base import NotificationProvider

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, provider: NotificationProvider) -> None:
        self._provider = provider

    def notify_decision(self, request: RequestModel, approved: bool) -> None:
        """Send approval or rejection notification; errors are swallowed."""
        try:
            self._provider.send_approval_notification(request, approved)
        except Exception as exc:
            logger.error("Notification failed for %s: %s", request.display_id, exc)

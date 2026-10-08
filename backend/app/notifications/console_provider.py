"""[DEMO - không gửi email thật] Console notification provider.

Logs all notifications to stdout/console with a clear DEMO label.
"""
from __future__ import annotations

import logging

from app.notifications.base import NotificationProvider
from app.models.request import RequestModel

logger = logging.getLogger(__name__)


class ConsoleNotificationProvider(NotificationProvider):
    """Prints approval/rejection notifications to console (demo only)."""

    def send_approval_notification(
        self,
        request: RequestModel,
        approved: bool,
    ) -> None:
        verb = "APPROVED" if approved else "REJECTED"
        separator = "=" * 60
        logger.info(
            "\n%s\n"
            "[DEMO - không gửi email thật] NOTIFICATION\n"
            "To: %s <%s>\n"
            "Request: %s | Equipment: %s | Qty: %d\n"
            "Status: %s\n"
            "%s",
            separator,
            request.requester_name,
            request.requester_email or "N/A",
            request.display_id,
            request.equipment_id,
            request.quantity,
            verb,
            separator,
        )

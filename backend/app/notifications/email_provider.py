"""Email notification provider (stub).

Reads SMTP configuration from environment. In V1 this is a stub that
logs a warning - full implementation would use smtplib/aiosmtplib.
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.notifications.base import NotificationProvider
from app.models.request import RequestModel

logger = logging.getLogger(__name__)


class EmailNotificationProvider(NotificationProvider):
    """Stub email provider - reads SMTP config but does not send in V1."""

    def send_approval_notification(
        self,
        request: RequestModel,
        approved: bool,
    ) -> None:
        if not settings.SMTP_USER:
            logger.warning(
                "[EMAIL PROVIDER] SMTP not configured. "
                "Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD in .env to enable real emails."
            )
            return

        verb = "đã được DUYỆT" if approved else "đã bị TỪ CHỐI"
        subject = f"[Yêu cầu mượn thiết bị] {request.display_id} {verb}"
        body = (
            f"Xin chào {request.requester_name},\n\n"
            f"Yêu cầu mượn thiết bị của bạn ({request.display_id}) {verb}.\n"
            f"Thiết bị: {request.equipment_id}\n"
            f"Số lượng: {request.quantity}\n"
            f"Thời gian: {request.needed_from} đến {request.needed_to}\n\n"
            "Trân trọng,\nHệ thống quản lý thiết bị"
        )

        # Stub: log instead of sending
        logger.info(
            "[EMAIL STUB] Would send email to %s\nSubject: %s\n%s",
            request.requester_email,
            subject,
            body,
        )

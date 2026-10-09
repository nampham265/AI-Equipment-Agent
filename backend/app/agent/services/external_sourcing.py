"""External sourcing service abstraction.

Handles external product searches, vendors, and pricing.
Strictly protects internal data and ensures truthfulness.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class SourcedProduct(BaseModel):
    product_name: str
    shop_name: str
    price: Optional[float] = None
    currency: str = "VND"
    url: str
    source: str
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    availability: str = "Chưa rõ"
    notes: Optional[str] = None


class ExternalSourcingResult(BaseModel):
    enabled: bool
    status: str  # "success" | "disabled" | "not_configured" | "no_results" | "error"
    query_used: str
    products: list[SourcedProduct] = Field(default_factory=list)
    message: str


class ExternalSourcingService:
    """Service handling supplier searches outside the internal warehouse."""

    def __init__(self, enabled: Optional[bool] = None) -> None:
        self._enabled = enabled if enabled is not None else settings.ENABLE_EXTERNAL_SOURCING

    def search_sources(
        self,
        product_query: str,
        constraints: Optional[dict[str, Any]] = None,
        max_results: int = 3,
    ) -> ExternalSourcingResult:
        """Search external suppliers. If disabled or unconfigured, returns honest status."""
        clean_query = self._sanitize_query(product_query)

        if not self._enabled:
            return ExternalSourcingResult(
                enabled=False,
                status="disabled",
                query_used=clean_query,
                products=[],
                message=(
                    "Dịch vụ tìm kiếm nguồn cung ứng bên ngoài (External Sourcing) hiện đang tắt "
                    "hoặc chưa được cấu hình nhà cung cấp chính thức. "
                    "Vui lòng liên hệ phòng mua hàng (Purchasing) để được hỗ trợ mua mới."
                ),
            )

        # In production when enabled with real vendor API/Gemini web grounding
        # We enforce NO fabricated data: every product must have verified source and URL
        return ExternalSourcingResult(
            enabled=True,
            status="not_configured",
            query_used=clean_query,
            products=[],
            message="Chưa cấu hình API nhà cung cấp bên ngoài (DigiKey/Mouser/Shopee Mall).",
        )

    def sanitize_query(self, query: str) -> str:
        """Strips internal project names or confidential words from external queries."""
        import re
        sanitized = query
        for sensitive in ["project alpha", "project beta", "bosch", "dự án alpha", "dự án beta", "alpha", "beta", "tủ 1", "tủ 2", "tủ 3"]:
            pattern = re.compile(re.escape(sensitive), re.IGNORECASE)
            sanitized = pattern.sub("", sanitized)
        # Strip emails
        sanitized = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "", sanitized)
        return " ".join(sanitized.split())

    _sanitize_query = sanitize_query

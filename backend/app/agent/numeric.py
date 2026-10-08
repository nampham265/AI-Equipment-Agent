"""Deterministic arithmetic and availability comparison for Agent Orchestration."""
from __future__ import annotations

from typing import Optional


class NumericExplanation:
    """Format exact mathematical explanations for quantities and shortages."""

    @staticmethod
    def explain_quantity(
        equipment_id: str,
        equipment_name: str,
        total_quantity: int,
        available_quantity: int,
        requested_quantity: Optional[int] = None,
        unit: str = "cái",
        has_date_range: bool = False,
    ) -> str:
        """Produce deterministic arithmetic statement without hallucination."""
        if requested_quantity is None or requested_quantity <= 0:
            if available_quantity < total_quantity:
                return (
                    f"Thiết bị **{equipment_name}** (`{equipment_id}`) hiện ghi nhận tổng cộng **{total_quantity} {unit}** "
                    f"trong kho (trong đó hiện có **{available_quantity} {unit}** chưa bị giữ lịch mượn)."
                )
            return (
                f"Thiết bị **{equipment_name}** (`{equipment_id}`) hiện ghi nhận tổng cộng **{total_quantity} {unit}** "
                f"trong kho."
            )

        # When requested quantity exceeds total inventory
        if requested_quantity > total_quantity:
            shortage = requested_quantity - total_quantity
            return (
                f"Kho hiện ghi nhận {total_quantity} {unit} {equipment_id}, nên không đủ {requested_quantity} {unit}. "
                f"Số lượng thiếu là {shortage} {unit}."
            )

        # When requested quantity <= total inventory, but date range is not specified
        if not has_date_range:
            return (
                f"Kho hiện ghi nhận tổng cộng {total_quantity} {unit} {equipment_id}. "
                f"Tuy nhiên, hệ thống hiện chưa có đủ dữ liệu mượn/trả để xác nhận số lượng thực tế "
                f"đang sẵn sàng trong khoảng thời gian bạn cần."
            )

        # When date range is specified and checked
        if requested_quantity <= available_quantity:
            return (
                f"Thiết bị **{equipment_name}** (`{equipment_id}`) có **{available_quantity} {unit}** khả dụng "
                f"trong khoảng thời gian bạn yêu cầu, đáp ứng đủ số lượng **{requested_quantity} {unit}** bạn cần."
            )

        shortage = requested_quantity - available_quantity
        return (
            f"Trong khoảng thời gian yêu cầu, thiết bị **{equipment_name}** (`{equipment_id}`) chỉ còn "
            f"**{available_quantity} {unit}** khả dụng (tổng kho: {total_quantity} {unit}). "
            f"Bạn đang yêu cầu **{requested_quantity} {unit}**, tức là đang **thiếu {shortage} {unit}**."
        )

    @staticmethod
    def explain_sufficiency(
        equipment_id: str,
        equipment_name: str,
        total_quantity: int,
        available_quantity: int,
        requested_quantity: int,
        unit: str = "cái",
        has_date_range: bool = False,
    ) -> str:
        """Deterministic response for 'có đủ X cái không?' queries."""
        if requested_quantity > total_quantity:
            shortage = requested_quantity - total_quantity
            return (
                f"Kho hiện ghi nhận {total_quantity} {unit} {equipment_id}, nên không đủ {requested_quantity} {unit}. "
                f"Số lượng thiếu là {shortage} {unit}."
            )

        if not has_date_range:
            return (
                f"Kho hiện ghi nhận tổng cộng {total_quantity} {unit} {equipment_id}. "
                f"Tuy nhiên, hệ thống hiện chưa có đủ dữ liệu mượn/trả để xác nhận số lượng thực tế "
                f"đang sẵn sàng trong khoảng thời gian bạn cần."
            )

        if requested_quantity <= available_quantity:
            return (
                f"Kho hiện có đủ {requested_quantity} {unit} {equipment_id} khả dụng "
                f"trong khoảng thời gian bạn yêu cầu ({available_quantity}/{total_quantity} {unit})."
            )

        shortage = requested_quantity - available_quantity
        return (
            f"Kho hiện không đủ {requested_quantity} {unit} {equipment_id} trong thời gian yêu cầu "
            f"(khả dụng: {available_quantity} {unit}, tổng kho: {total_quantity} {unit}). "
            f"Số lượng thiếu là {shortage} {unit}."
        )

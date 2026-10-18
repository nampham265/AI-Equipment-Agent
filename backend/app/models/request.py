"""SQLAlchemy ORM model for EquipmentRequest."""
from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RequestModel(Base):
    __tablename__ = "equipment_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requester_name: Mapped[str] = mapped_column(String, nullable=False)
    requester_email: Mapped[str | None] = mapped_column(String, nullable=True)
    project: Mapped[str] = mapped_column(String, nullable=False)
    equipment_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    needed_from: Mapped[str] = mapped_column(String, nullable=False)  # ISO date string
    needed_to: Mapped[str] = mapped_column(String, nullable=False)    # ISO date string
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    priority_level: Mapped[str] = mapped_column(String, nullable=False, default="Needs review")
    priority_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="Pending", index=True)
    return_condition: Mapped[str | None] = mapped_column(String, nullable=True)
    return_condition_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    returned_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)   # ISO datetime string
    modified_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO datetime string
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def display_id(self) -> str:
        return f"REQ-{self.id:06d}"

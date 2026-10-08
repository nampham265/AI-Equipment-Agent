"""Dataclass representing a row in the Users worksheet of equipment_agent.xlsx."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExcelUserModel:
    user_email: str
    user_name: str
    role: str  # USER, MANAGER, ADMIN
    is_active: bool

    @property
    def is_admin(self) -> bool:
        return self.role.upper() == "ADMIN"

    @property
    def is_manager(self) -> bool:
        return self.role.upper() in ("MANAGER", "ADMIN")

    @property
    def is_user(self) -> bool:
        return self.role.upper() == "USER"

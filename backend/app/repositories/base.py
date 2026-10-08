"""Abstract repository interfaces (ports).

Concrete implementations (SQLite adapters) live in sqlite_*.py files.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.equipment import EquipmentModel
from app.models.request import RequestModel


class EquipmentRepository(ABC):
    """Port for Equipment data access."""

    @abstractmethod
    def list_all(self) -> list[EquipmentModel]:
        ...

    @abstractmethod
    def search(self, query: str) -> list[EquipmentModel]:
        ...

    @abstractmethod
    def get_by_id(self, equipment_id: str) -> EquipmentModel | None:
        ...

    @abstractmethod
    def count(self) -> int:
        ...

    @abstractmethod
    def bulk_upsert(self, items: list[EquipmentModel]) -> None:
        ...


class RequestRepository(ABC):
    """Port for EquipmentRequest data access."""

    @abstractmethod
    def create(self, request: RequestModel) -> RequestModel:
        ...

    @abstractmethod
    def get_by_id(self, request_id: int) -> RequestModel | None:
        ...

    @abstractmethod
    def list_by_requester(self, requester_email: str) -> list[RequestModel]:
        ...

    @abstractmethod
    def list_all(self, status: str | None = None) -> list[RequestModel]:
        ...

    @abstractmethod
    def update(self, request: RequestModel) -> RequestModel:
        ...

    @abstractmethod
    def get_overlapping(
        self,
        equipment_id: str,
        needed_from: str,
        needed_to: str,
        statuses: list[str],
        exclude_id: int | None = None,
    ) -> list[RequestModel]:
        ...

    @abstractmethod
    def count_by_status(self) -> dict[str, int]:
        ...


class UserRepository(ABC):
    """Port for User data access."""

    @abstractmethod
    def list_all(self) -> list:
        ...

    @abstractmethod
    def get_by_email(self, email: str):
        ...

    @abstractmethod
    def create_user(self, user_in):
        ...

    @abstractmethod
    def update_role(self, email: str, new_role: str, admin_email: str):
        ...

    @abstractmethod
    def set_active(self, email: str, is_active: bool, admin_email: str):
        ...

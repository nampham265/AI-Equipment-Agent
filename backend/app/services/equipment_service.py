"""Equipment service - business logic for equipment lookup."""
from __future__ import annotations

from app.models.equipment import EquipmentModel
from app.repositories.base import EquipmentRepository
from app.schemas.equipment import EquipmentRead


class EquipmentService:
    def __init__(self, repo: EquipmentRepository) -> None:
        self._repo = repo

    def list_equipment(self, query: str | None = None) -> list[EquipmentRead]:
        if query and query.strip():
            items = self._repo.search(query.strip())
        else:
            items = self._repo.list_all()
        return [EquipmentRead.model_validate(item) for item in items]

    def get_equipment(self, equipment_id: str) -> EquipmentRead | None:
        item = self._repo.get_by_id(equipment_id)
        if item is None:
            return None
        return EquipmentRead.model_validate(item)

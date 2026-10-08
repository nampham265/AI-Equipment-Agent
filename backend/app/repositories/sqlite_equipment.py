"""SQLite implementation of EquipmentRepository."""
from __future__ import annotations

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.models.equipment import EquipmentModel
from app.repositories.base import EquipmentRepository


class SQLiteEquipmentRepository(EquipmentRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_all(self) -> list[EquipmentModel]:
        return self._db.query(EquipmentModel).order_by(EquipmentModel.equipment_name).all()

    def search(self, query: str) -> list[EquipmentModel]:
        q = f"%{query}%"
        return (
            self._db.query(EquipmentModel)
            .filter(
                or_(
                    EquipmentModel.equipment_name.ilike(q),
                    EquipmentModel.equipment_id.ilike(q),
                    EquipmentModel.category.ilike(q),
                    EquipmentModel.description.ilike(q),
                )
            )
            .order_by(EquipmentModel.equipment_name)
            .all()
        )

    def get_by_id(self, equipment_id: str) -> EquipmentModel | None:
        return self._db.get(EquipmentModel, equipment_id)

    def count(self) -> int:
        return self._db.query(func.count(EquipmentModel.equipment_id)).scalar() or 0

    def bulk_upsert(self, items: list[EquipmentModel]) -> None:
        for item in items:
            existing = self._db.get(EquipmentModel, item.equipment_id)
            if existing:
                existing.equipment_name = item.equipment_name
                existing.category = item.category
                existing.description = item.description
                existing.quantity_total = item.quantity_total
                existing.unit = item.unit
                existing.location = item.location
            else:
                self._db.add(item)
        self._db.commit()

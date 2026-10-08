"""Standalone seed script.

Run from the backend/ directory:
    python seed_db.py

Seeds the SQLite database from data/sample/equipment.csv.
"""
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    # Ensure the app package is importable when run from backend/
    sys.path.insert(0, str(Path(__file__).parent))

    from app.core.database import create_all_tables, SessionLocal
    from app.models.equipment import EquipmentModel
    from app.repositories.sqlite_equipment import SQLiteEquipmentRepository

    create_all_tables()

    # CSV relative to workspace root (parent of backend/)
    csv_path = Path(__file__).resolve().parents[1] / "data" / "sample" / "equipment.csv"
    if not csv_path.exists():
        logger.error("CSV not found at %s", csv_path)
        sys.exit(1)

    items: list[EquipmentModel] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                qty = int(row.get("Quantity", 0))
            except ValueError:
                qty = 0
            items.append(
                EquipmentModel(
                    equipment_id=row.get("EquipmentID", "").strip(),
                    equipment_name=row.get("EquipmentName", "").strip(),
                    category=row.get("Category", "").strip() or None,
                    description=row.get("Description", "").strip() or None,
                    quantity_total=qty,
                    unit=row.get("Unit", "").strip() or None,
                    location=row.get("Location", "").strip() or None,
                )
            )

    db = SessionLocal()
    try:
        repo = SQLiteEquipmentRepository(db)
        existing = repo.count()
        repo.bulk_upsert(items)
        logger.info(
            "Seeded %d records (was %d before). DB: %s",
            len(items),
            existing,
            csv_path.parent,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

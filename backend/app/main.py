"""FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.database import create_all_tables
from app.api import equipment as equipment_router
from app.api import agent as agent_router
from app.api import requests as requests_router
from app.api import manager as manager_router
from app.api import admin as admin_router
from app.api import health as health_router
from app.auth.router import router as auth_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Equipment Agent V1",
    description="Backend for the AI Equipment Management application.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Middlewares
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.APP_SECRET_KEY,
    session_cookie="oauth_session",
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(equipment_router.router)
app.include_router(agent_router.router)
app.include_router(requests_router.router)
app.include_router(manager_router.router)
app.include_router(admin_router.router)
app.include_router(health_router.router)
app.include_router(auth_router)

# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------
from fastapi.responses import JSONResponse
from fastapi import Request
from app.repositories.excel_request import ExcelFileLockedError

@app.exception_handler(ExcelFileLockedError)
def excel_file_locked_handler(request: Request, exc: ExcelFileLockedError):
    return JSONResponse(
        status_code=423,
        content={"detail": str(exc)},
    )

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup() -> None:
    logger.info("Starting up AI Equipment Agent V1 (Data backend: %s)...", settings.DATA_BACKEND)
    if settings.DATA_BACKEND == "excel":
        excel_path = settings.resolved_excel_path
        if not excel_path.exists():
            logger.error("CRITICAL: Excel workbook not found at %s", excel_path)
            raise FileNotFoundError(f"Excel workbook not found at {excel_path}. Please check EXCEL_DATA_PATH.")
        try:
            from app.repositories.excel_equipment import ExcelEquipmentRepository
            from app.repositories.excel_request import ExcelRequestRepository
            from app.repositories.excel_user import ExcelUserRepository
            eq_repo = ExcelEquipmentRepository(str(excel_path))
            req_repo = ExcelRequestRepository(str(excel_path))
            user_repo = ExcelUserRepository(str(excel_path))
            
            users = user_repo.list_all()
            active_admins = [u for u in users if u.role == "ADMIN" and u.is_active]
            if not active_admins:
                logger.warning("WARNING: No active ADMIN found in Users sheet! Please ensure at least one active ADMIN is configured.")
            logger.info(
                "Excel workbook validated successfully. Total equipment: %d, Total users: %d (Active admins: %d)",
                eq_repo.count(),
                len(users),
                len(active_admins),
            )
        except Exception as exc:
            logger.error("CRITICAL: Failed to validate Excel workbook schema: %s", exc)
            raise RuntimeError(f"Excel workbook schema error: {exc}") from exc
    elif settings.DATA_BACKEND == "sqlite":
        create_all_tables()
        _seed_if_empty()


def _seed_if_empty() -> None:
    """Seed the database from CSV if equipment table is empty."""
    from app.core.database import SessionLocal
    from app.repositories.sqlite_equipment import SQLiteEquipmentRepository

    db = SessionLocal()
    try:
        repo = SQLiteEquipmentRepository(db)
        if repo.count() == 0:
            logger.info("Equipment table is empty - seeding from CSV...")
            _run_seed(db)
        else:
            logger.info("Equipment table already has data - skipping seed.")
    finally:
        db.close()


def _run_seed(db) -> None:
    """Load equipment.csv and bulk upsert into DB."""
    import csv
    from pathlib import Path
    from app.models.equipment import EquipmentModel
    from app.repositories.sqlite_equipment import SQLiteEquipmentRepository

    csv_path = Path(__file__).resolve().parents[2] / "data" / "sample" / "equipment.csv"

    if not csv_path.exists():
        logger.warning("Seed CSV not found at %s - skipping seed.", csv_path)
        return

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

    repo = SQLiteEquipmentRepository(db)
    repo.bulk_upsert(items)
    logger.info("Seeded %d equipment records from CSV.", len(items))

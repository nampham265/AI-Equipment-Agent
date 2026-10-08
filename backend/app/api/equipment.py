"""Equipment API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.repositories.factory import get_equipment_repo, get_request_repo
from app.schemas.equipment import EquipmentAvailability, EquipmentRead
from app.services.availability_service import AvailabilityService
from app.services.equipment_service import EquipmentService

router = APIRouter(prefix="/api/equipment", tags=["equipment"])


def _eq_service(db: Session = Depends(get_db)) -> EquipmentService:
    return EquipmentService(get_equipment_repo(db))


def _av_service(db: Session = Depends(get_db)) -> AvailabilityService:
    return AvailabilityService(get_request_repo(db))


@router.get("", response_model=list[EquipmentRead])
def list_equipment(
    q: str | None = Query(default=None, description="Search query"),
    service: EquipmentService = Depends(_eq_service),
) -> list[EquipmentRead]:
    """List or search all equipment."""
    return service.list_equipment(q)


@router.get("/{equipment_id}", response_model=EquipmentRead)
def get_equipment(
    equipment_id: str,
    service: EquipmentService = Depends(_eq_service),
) -> EquipmentRead:
    """Get a single piece of equipment by ID."""
    item = service.get_equipment(equipment_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy thiết bị '{equipment_id}'.",
        )
    return item


@router.get("/{equipment_id}/availability", response_model=EquipmentAvailability)
def check_availability(
    equipment_id: str,
    needed_from: str = Query(..., description="ISO date YYYY-MM-DD"),
    needed_to: str = Query(..., description="ISO date YYYY-MM-DD"),
    eq_service: EquipmentService = Depends(_eq_service),
    av_service: AvailabilityService = Depends(_av_service),
) -> EquipmentAvailability:
    """Check equipment availability for a date range."""
    equipment = eq_service.get_equipment(equipment_id)
    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy thiết bị '{equipment_id}'.",
        )
    if needed_from > needed_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="needed_from phải nhỏ hơn hoặc bằng needed_to.",
        )
    return av_service.calculate(
        equipment_id=equipment_id,
        needed_from=needed_from,
        needed_to=needed_to,
        quantity_total=equipment.quantity_total,
    )

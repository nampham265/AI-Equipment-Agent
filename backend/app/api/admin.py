"""Admin API routes - User Management and System Administration."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.session import SessionData
from app.core.deps import require_admin
from app.models.excel_user import ExcelUserModel
from app.repositories.factory import get_user_repo
from app.schemas.users import (
    UserActiveUpdate,
    UserCreate,
    UserRead,
    UserRoleUpdate,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserRead])
def list_users(current_admin: SessionData = Depends(require_admin)) -> list[UserRead]:
    """List all users in the Users worksheet (Admin only)."""
    repo = get_user_repo()
    users = repo.list_all()
    return [
        UserRead(
            user_email=u.user_email,
            user_name=u.user_name,
            role=u.role,
            is_active=u.is_active,
        )
        for u in users
    ]


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    current_admin: SessionData = Depends(require_admin),
) -> UserRead:
    """Add a new USER or MANAGER to the Users worksheet (Admin only)."""
    repo = get_user_repo()
    try:
        new_user = ExcelUserModel(
            user_email=str(body.user_email).strip(),
            user_name=body.user_name.strip(),
            role=body.role.value,
            is_active=True,
        )
        created = repo.create(new_user)
        return UserRead(
            user_email=created.user_email,
            user_name=created.user_name,
            role=created.role,
            is_active=created.is_active,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch("/users/{user_email}/role", response_model=UserRead)
def update_user_role(
    user_email: str,
    body: UserRoleUpdate,
    current_admin: SessionData = Depends(require_admin),
) -> UserRead:
    """Change user role (USER <-> MANAGER). Protects final active ADMIN from demotion."""
    repo = get_user_repo()
    try:
        updated = repo.update_role(user_email, body.role.value)
        return UserRead(
            user_email=updated.user_email,
            user_name=updated.user_name,
            role=updated.role,
            is_active=updated.is_active,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch("/users/{user_email}/active", response_model=UserRead)
def update_user_active(
    user_email: str,
    body: UserActiveUpdate,
    current_admin: SessionData = Depends(require_admin),
) -> UserRead:
    """Activate or deactivate a user. Protects final active ADMIN from deactivation."""
    repo = get_user_repo()
    try:
        updated = repo.set_active(user_email, body.is_active)
        return UserRead(
            user_email=updated.user_email,
            user_name=updated.user_name,
            role=updated.role,
            is_active=updated.is_active,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
